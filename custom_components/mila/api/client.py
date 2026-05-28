"""Async GraphQL client for the live Mila API.

Two classes live here:

* `MilaClient` is a low-level executor. Give it an aiohttp `ClientSession`
  and a coroutine that returns a valid bearer token, and call
  `execute(query, variables)` to send a request. It handles status-code
  retries and converts unexpected responses into our two exception types.

* `MilaApi` wraps `MilaClient` with one method per real operation
  (`get_account`, `get_appliances`, `apply_smart_mode`, ...). The rest of
  the integration only touches `MilaApi`; the lower-level client is
  exposed for tests and the local probe script.

A note on coercion: the Mila GraphQL server emits a few values that
aren't naturally JSON. `installedAt` / `calibratedAt` come back as
integer Unix seconds (custom `EpochSecond` scalar); `instant` fields on
sensor readings come back as ISO-8601 strings with a trailing `Z`. Both
are easier to consume as `datetime` objects downstream, so we walk the
decoded payload and rewrite those fields in place.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from aiohttp import ClientError, ClientSession

from .enums import (
    ApplianceSensorKind,
    FanSpeed,
    PerformanceMode,
    PerformanceProfile,
    SmartModeKind,
    SoundsConfig,
)
from .exceptions import MilaError, OAuthError
from .queries import (
    APPLY_ROOM_BEDTIME,
    APPLY_ROOM_PERFORMANCE_CONFIG,
    APPLY_ROOM_SOUNDS_CONFIG,
    FORCE_ROOM_DATA,
    GET_APPLIANCES,
    GET_LOCATIONS,
    GET_OWNER_PROFILE,
    GRAPHQL_URL,
    smart_mode_mutation,
    smart_mode_supported,
)

_LOGGER = logging.getLogger(__name__)


# Field names whose value is an integer Unix-seconds timestamp and should
# be coerced to a tz-aware UTC `datetime` before being handed to callers.
# Mila's `EpochSecond` scalar shows up on filter dates today; if more
# fields adopt it, add the names here.
_EPOCH_FIELDS = ("installedAt", "calibratedAt")

# Field names whose value is an ISO-8601 string (with a trailing `Z` for
# UTC). Currently just the `instant` field on `InstantValue`.
_INSTANT_FIELDS = ("instant",)


# A coroutine that returns a non-expired access token. The auth module
# defines the real implementation (`MilaConfigEntryAuth.async_get_access_
# token`). We accept it as a callable rather than holding the session
# directly so the client doesn't need to know how tokens are stored or
# refreshed.
TokenProvider = Callable[[], Awaitable[str]]


def _coerce_epoch_seconds(value: Any) -> Optional[datetime]:
    """Turn an integer Unix-seconds value into a tz-aware UTC datetime.

    Returns `None` for `None` / non-numeric input rather than raising:
    the API occasionally returns null for a field that we'd otherwise
    expect to be a timestamp (e.g. a brand-new filter that hasn't been
    calibrated yet).
    """
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _coerce_instant(value: Any) -> Any:
    """Turn an ISO-8601 string with a trailing `Z` into a `datetime`.

    Python's `datetime.fromisoformat` handles `+00:00` but not the
    shorthand `Z`, so we substitute. Returns the original value unchanged
    if it isn't a recognised string.
    """
    if value is None or not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Leave odd strings alone (e.g. a sentinel like "n/a") rather
        # than mask the issue with `None`.
        return value


def _coerce_scalars_in_place(node: Any) -> None:
    """Walk a GraphQL response and convert known scalar fields in place.

    Mutates the input rather than copying so we don't pay an O(n)
    duplication cost on large payloads (the `GET_APPLIANCES` response
    nests sensors, smart modes, performance config, filter, and state
    underneath each appliance).
    """
    if isinstance(node, dict):
        # `list(node.items())` because we mutate the dict during iteration.
        for key, val in list(node.items()):
            if key in _EPOCH_FIELDS:
                node[key] = _coerce_epoch_seconds(val)
            elif key in _INSTANT_FIELDS:
                node[key] = _coerce_instant(val)
            else:
                _coerce_scalars_in_place(val)
    elif isinstance(node, list):
        for item in node:
            _coerce_scalars_in_place(item)


class MilaClient:
    """Low-level GraphQL client. One instance per coordinator.

    The client is intentionally cheap to construct: it only holds two
    references (the shared aiohttp session and the token provider) and
    has no per-instance cache. State lives in the coordinator and
    `OAuth2Session`.
    """

    def __init__(self, session: ClientSession, token_provider: TokenProvider) -> None:
        """Wire up the client.

        Args:
            session: aiohttp client session, normally the HA-managed one
                (`aiohttp_client.async_get_clientsession`). We never
                close this from here; it's owned by Home Assistant.
            token_provider: coroutine returning a current access token.
                Called before every request so the cached token can be
                refreshed transparently.
        """
        self._session = session
        self._token_provider = token_provider

    async def execute(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        *,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Send a GraphQL query/mutation and return the decoded `data`.

        Retries on the transient error classes a remote API can return:

        * HTTP 429 — back off exponentially (capped at 30 s) and retry.
        * HTTP 401 — request a fresh token on the next loop iteration and
          retry; bail out after two consecutive 401s (the refresh token
          itself must be invalid in that case).
        * HTTP 5xx — short back-off (capped at 5 s) and retry.
        * Transport error from aiohttp — small back-off and retry.

        Anything else (4xx other than 401/429, GraphQL `errors` array)
        raises immediately so the caller sees the failure on the first
        poll instead of waiting for retries to exhaust.

        Args:
            query: GraphQL document string.
            variables: optional dict of variable values.
            max_retries: attempts before giving up.

        Returns:
            The `data` payload from a successful response, with scalar
            coercion applied (`installedAt`, `instant`, etc.).

        Raises:
            OAuthError: token provider failed, repeated 401s.
            MilaError: GraphQL errors, malformed response, exhausted
                retries.
        """
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        # Counter for *consecutive* HTTP 401s. We tolerate one (the cached
        # token may simply have expired between coordinator polls and a
        # refresh wasn't yet triggered) but bail on the second; that
        # signals the refresh token itself is no longer accepted.
        auth_errors = 0
        # Keep the last HTTP status / body around so the eventual
        # `MilaError` after exhausting retries carries a useful message.
        last_status: Optional[int] = None
        last_body: Any = None

        for attempt in range(max_retries):
            # Always fetch a fresh token before each attempt. The token
            # provider knows whether to return a cached one or refresh.
            try:
                token = await self._token_provider()
            except OAuthError:
                # The provider already wrapped this; just re-raise.
                raise
            except Exception as ex:
                # Anything else from the provider is unexpected. Treat as
                # an auth problem because we can't make requests without
                # a token regardless of the root cause.
                raise OAuthError(f"Could not obtain access token: {ex}") from ex

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            try:
                async with self._session.post(
                    GRAPHQL_URL, json=payload, headers=headers
                ) as resp:
                    last_status = resp.status
                    # Read the body as text once; we re-parse it as JSON
                    # only when the status code looks promising.
                    text = await resp.text()

                    if resp.status == 429:
                        # Mila has occasionally throttled bursty clients.
                        # Exponential back-off capped at 30 s; we don't
                        # bother reading the Retry-After header because
                        # it isn't always present.
                        await asyncio.sleep(min(30, 2 ** attempt))
                        continue

                    if resp.status == 401:
                        auth_errors += 1
                        if auth_errors >= 2:
                            raise OAuthError(
                                "Repeated 401 responses; token appears invalid"
                            )
                        # One 401 might just mean the token rotated
                        # between fetch and request. Loop around so the
                        # provider can hand us a fresh one.
                        continue

                    if resp.status >= 500:
                        # Server-side hiccup. Linear back-off — usually
                        # one retry is enough.
                        await asyncio.sleep(min(5, 1 + attempt))
                        continue

                    if resp.status >= 400:
                        # 4xx other than 401/429 aren't going to fix
                        # themselves on retry. Surface immediately.
                        raise MilaError(
                            f"Mila API HTTP {resp.status}: {text[:300]}"
                        )

                    try:
                        body = await resp.json(content_type=None)
                    except ValueError as ex:
                        raise MilaError(
                            f"Mila API returned non-JSON: {text[:300]}"
                        ) from ex
                    last_body = body

                    # GraphQL errors come back as 200 OK with an `errors`
                    # array. We treat any non-empty errors array as a
                    # hard failure because the caller's `data` payload
                    # is almost certainly incomplete.
                    if "errors" in body and body["errors"]:
                        raise MilaError(f"GraphQL errors: {body['errors']}")

                    data = body.get("data")
                    if data is None:
                        raise MilaError(f"GraphQL response missing data: {body}")

                    _coerce_scalars_in_place(data)
                    return data
            except ClientError as ex:
                if attempt + 1 >= max_retries:
                    raise MilaError(f"Mila API transport error: {ex}") from ex
                await asyncio.sleep(min(5, 1 + attempt))

        # All retries used without a successful return. Include enough
        # context for diagnostics without flooding the log.
        raise MilaError(
            f"Mila API call did not succeed after {max_retries} attempts "
            f"(last_status={last_status}, last_body={str(last_body)[:200]!r})"
        )


class MilaApi:
    """High-level facade with one method per real API operation.

    The rest of the integration (config flow, coordinator, device
    wrappers) talks to this class rather than to `MilaClient` directly.
    Method names mirror the operations the legacy SDK exposed, which
    keeps diff size manageable.
    """

    def __init__(self, client: MilaClient) -> None:
        self._client = client

    # ----- Reads -------------------------------------------------------

    async def get_account(self) -> Dict[str, Any]:
        """Return `owner.profile` ({email, firstName, lastName})."""
        data = await self._client.execute(GET_OWNER_PROFILE)
        return data["owner"]["profile"]

    async def get_appliances(self) -> List[Dict[str, Any]]:
        """Return every appliance on the account in one round trip.

        Each item carries room, state, filter, smartModes,
        performanceConfig and the full sensor set. See `GET_APPLIANCES`
        in `queries.py`.
        """
        data = await self._client.execute(GET_APPLIANCES)
        return data["owner"]["appliances"] or []

    async def get_location_data(self) -> List[Dict[str, Any]]:
        """Return every household location and its outdoor air station."""
        data = await self._client.execute(GET_LOCATIONS)
        return data["owner"]["locations"] or []

    # ----- Writes ------------------------------------------------------

    async def force_room_data(self, room_id: str) -> None:
        """Ask the appliance for an immediate sensor data push.

        Used after a manual fan-speed change so the next coordinator
        refresh reflects the new RPM. The mutation returns just the
        room id; we don't care about the value so the result is
        discarded.
        """
        await self._client.execute(FORCE_ROOM_DATA, {"roomId": str(room_id)})

    async def apply_local_bedtime(
        self, room_id: str, local_start: str, local_end: str
    ) -> None:
        """Set the room's nighttime window via the `mila.set_bedtime` service.

        Times are local-only strings (`HH:MM:SS`) interpreted in the
        room's location timezone by the server.
        """
        await self._client.execute(
            APPLY_ROOM_BEDTIME,
            {
                "roomId": str(room_id),
                "localStart": local_start,
                "localEnd": local_end,
            },
        )

    async def apply_performance_config(
        self,
        room_id: str,
        *,
        mode: PerformanceMode | str,
        profile: PerformanceProfile | str = PerformanceProfile.Normal,
        fan_speed: FanSpeed | str = FanSpeed.Speed50,
    ) -> Dict[str, Any]:
        """Set the room's mode/profile/fan-speed in one call.

        Accepts either enum members or raw strings (the `_StrValueEnum`
        members are `str` subclasses, so callers can pass either). The
        server requires every input field every time, so callers must
        carry forward any value they don't want to change.

        Returns the resulting `performanceConfig` dict so the caller can
        sync local state without waiting for the next refresh.
        """
        result = await self._client.execute(
            APPLY_ROOM_PERFORMANCE_CONFIG,
            {
                "input": {
                    "roomId": str(room_id),
                    "mode": str(mode),
                    "profile": str(profile),
                    "fanSpeed": str(fan_speed),
                }
            },
        )
        return result["applyRoomPerformanceConfig"]["room"]["performanceConfig"]

    async def apply_sounds_config(
        self, room_id: str, sounds_config: SoundsConfig | str
    ) -> None:
        """Set the appliance sounds policy (Enabled / DaytimeOnly / Disabled)."""
        await self._client.execute(
            APPLY_ROOM_SOUNDS_CONFIG,
            {"roomId": str(room_id), "soundsConfig": str(sounds_config)},
        )

    async def apply_smart_mode(
        self,
        room_id: str,
        kind: SmartModeKind,
        is_enabled: bool,
        *,
        fan_mode: str = "Medium",
    ) -> None:
        """Toggle a single smart mode on or off.

        For Sleep/Turndown/Whitenoise the server requires a `fanMode`
        argument; we default to `Medium` because that matches what the
        Mila mobile app sends. If the caller wants a different speed
        they can override it.

        For any kind not in `_SMART_MODE_MUTATION_NAME` (currently none,
        but the check is here for future server-side removals), we log
        and return without sending a request, so a toggle UI never
        crashes.
        """
        if not smart_mode_supported(kind):
            _LOGGER.debug(
                "Smart mode %s not supported on live API; skipping", kind
            )
            return
        mutation = smart_mode_mutation(kind)
        variables: Dict[str, Any] = {
            "roomId": str(room_id),
            "isEnabled": bool(is_enabled),
        }
        if kind in {SmartModeKind.Sleep, SmartModeKind.Turndown, SmartModeKind.Whitenoise}:
            variables["fanMode"] = fan_mode
        await self._client.execute(mutation, variables)

    # ----- Helpers (no I/O) -------------------------------------------

    def sensors_payload_to_dict(
        self, sensors: Iterable[Dict[str, Any]]
    ) -> Dict[ApplianceSensorKind, Any]:
        """Index a sensors list by `ApplianceSensorKind`.

        Convenience method for callers that need O(1) lookup by sensor
        kind. We tolerate unknown kinds (skip them) so a server-side
        addition can't break existing clients.
        """
        out: Dict[ApplianceSensorKind, Any] = {}
        for sensor in sensors or []:
            kind_value = sensor.get("kind")
            try:
                out[ApplianceSensorKind(kind_value)] = sensor
            except ValueError:
                # Unknown sensor kind; ignore quietly.
                continue
        return out
