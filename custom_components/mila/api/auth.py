"""OAuth2 password grant + refresh against Mila's Keycloak realm.

Mila's mobile app is a public OAuth2 client: there is no client secret,
and the Keycloak realm `prod` exposes the standard OIDC token endpoint
under `id.milacares.com`. We use the **resource-owner password
credentials grant** to exchange (username, password) for an access token
plus a refresh token, then exchange the refresh token for new access
tokens as they expire.

This module is intentionally a pair of stateless coroutines rather than
a class. State (the live token, expiry timestamps, etc.) belongs to the
caller. In this integration the caller is Home Assistant's
`config_entry_oauth2_flow.OAuth2Session`, which persists the token dict
to the config entry on disk.

Error classification contract (the rest of the integration relies on
this, so treat it as an API):

* `OAuthError`  -> the auth server understood the request and rejected
                   it (wrong password, revoked refresh token, disabled
                   account). Only user action can fix it; the coordinator
                   promotes it to `ConfigEntryAuthFailed`, which halts
                   polling and prompts for reauthentication.
* `MilaError`   -> everything transient: transport failures, timeouts,
                   HTTP 5xx, throttling, and malformed response bodies.
                   The coordinator turns it into `UpdateFailed` (or
                   `ConfigEntryNotReady` during setup), both of which
                   retry automatically without bothering the user.

Getting this split wrong is expensive in the reauth direction: mapping a
network blip to `OAuthError` means one router hiccup at token-refresh
time permanently stops the integration until the user re-enters their
password.

Why not `async-oauthlib`?
  We previously pulled it in through `milasdk`. For a single grant type
  with a public client, the standard form-encoded POST in aiohttp is
  half a dozen lines and avoids the transitive dependency chain
  (`oauthlib`, `requests-oauthlib`, ...).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict

from aiohttp import ClientError, ClientSession, ClientTimeout

from .exceptions import MilaError, OAuthError

_LOGGER = logging.getLogger(__name__)

# Public OIDC endpoint addresses for Mila's identity provider.
AUTH_BASE_URL = "https://id.milacares.com"
TOKEN_ENDPOINT = f"{AUTH_BASE_URL}/auth/realms/prod/protocol/openid-connect/token"

# Public client_id used by the Mila mobile app; safe to ship in the repo.
CLIENT_ID = "prod-ui"

# The realm rejects comma-separated scope lists, so we keep this
# space-separated and matching what the mobile app sends.
SCOPE = "email profile"

# Hard cap on how long one token-endpoint request may take. Without an
# explicit timeout a hung TCP connection would block for aiohttp's
# 5-minute default, freezing whatever coordinator refresh or service
# call was waiting on the token.
TOKEN_REQUEST_TIMEOUT = ClientTimeout(total=30)

# HTTP statuses that mean "the grant itself was rejected". Anything else
# non-200 (5xx, 429, gateway weirdness) is treated as transient.
_REJECTED_STATUSES = (400, 401, 403)

# We pretend the token expires this many seconds early to avoid sending a
# request with a token that's about to be rejected by the server clock.
# Keycloak's default access-token TTL is ~5 minutes, so 5 seconds is
# plenty of headroom without forcing extra refreshes.
_CLOCK_SKEW_SECONDS = 5


def _annotate_expiry(token: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp absolute expiry timestamps onto a freshly returned token dict.

    The OIDC response gives durations (`expires_in`, `refresh_expires_in`)
    in seconds. Storing absolute Unix timestamps lets later code compare
    against `time.time()` directly without having to remember when the
    token was issued. Home Assistant's `OAuth2Session` looks for these
    keys, so we add both whenever the server includes the matching
    `expires_in` / `refresh_expires_in` field.
    """
    now = int(time.time())
    if "expires_in" in token:
        token["expires_at"] = (
            now + int(float(token["expires_in"])) - _CLOCK_SKEW_SECONDS
        )
    if "refresh_expires_in" in token:
        # Not every grant flow returns this, but Keycloak's password grant
        # does, and refresh tokens themselves expire (`offline` scope is
        # the only thing that wouldn't).
        token["refresh_expires_at"] = (
            now + int(float(token["refresh_expires_in"])) - _CLOCK_SKEW_SECONDS
        )
    return token


async def _post_token_request(
    session: ClientSession, data: Dict[str, str], context: str
) -> Dict[str, Any]:
    """POST one grant to the token endpoint and classify every outcome.

    Shared by `request_token` and `refresh_token` so the classification
    rules (see the module docstring) live in exactly one place.

    Args:
        session: aiohttp client session (shared with Home Assistant).
        data: the form-encoded grant payload.
        context: short label ("Token request" / "Token refresh") used to
            prefix error messages so logs say which grant failed.

    Returns:
        The decoded token dict, annotated with absolute expiry stamps.

    Raises:
        OAuthError: the server rejected the grant (HTTP 400/401/403).
        MilaError: transport failure, timeout, HTTP 5xx / throttling, or
            a malformed response body. All safe to retry automatically.
    """
    try:
        async with session.post(
            TOKEN_ENDPOINT, data=data, timeout=TOKEN_REQUEST_TIMEOUT
        ) as resp:
            status = resp.status
            # Read the body as text first: Keycloak itself always sends
            # JSON, but a reverse proxy or captive portal in front of it
            # can return an HTML error page. Parsing from text keeps the
            # raw body available for the error message either way.
            # errors="replace" so undecodable bytes flow into the JSON
            # guard below (transient) instead of escaping this function
            # as an unclassified UnicodeDecodeError, which downstream
            # code would misread as an auth failure.
            text = await resp.text(errors="replace")
            try:
                body = json.loads(text)
            except ValueError:
                # Non-JSON body. Keycloak never produces this, so we're
                # looking at infrastructure between us and the server.
                # That's transient, not a credential problem.
                raise MilaError(
                    f"{context} returned non-JSON (HTTP {status}): {text[:200]}"
                )

            if status == 200 and "access_token" in body:
                return _annotate_expiry(body)

            # Surface the most helpful field available: usually
            # error_description ("Invalid user credentials"), falling
            # back to error code, then the raw body.
            detail = body.get("error_description") or body.get("error") or body

            if status in _REJECTED_STATUSES:
                # The auth server actively refused the grant: wrong
                # password, revoked or expired refresh token, disabled
                # account. Retrying can't help; the user must act.
                raise OAuthError(f"{context} rejected (HTTP {status}): {detail}")

            # Everything else: 5xx during Keycloak maintenance, 429
            # throttling, or a 200 that inexplicably lacks a token.
            # These heal on their own, so classify as transient.
            raise MilaError(f"{context} failed (HTTP {status}): {detail}")
    except (ClientError, asyncio.TimeoutError) as ex:
        # Network-level failure (DNS, TLS, connection reset, timeout).
        # This says nothing about whether the credentials are valid, so
        # it must NOT become OAuthError: promoting a transient outage to
        # a reauth prompt would permanently halt polling until the user
        # manually re-enters a password that was never wrong.
        raise MilaError(f"{context} transport error: {ex}") from ex


async def request_token(
    session: ClientSession, username: str, password: str
) -> Dict[str, Any]:
    """Exchange (username, password) for a fresh OIDC token bundle.

    Used in two situations:

    1. During the initial config-flow setup, to verify the user typed
       the right credentials before saving the entry.
    2. As a fallback inside `MilaOauthImplementation._async_refresh_token`
       when the refresh token itself is no longer valid; rather than
       force the user to reauthenticate via the UI, we re-run the
       password grant with the credentials we already have stored.

    Args:
        session: aiohttp client session (shared with Home Assistant).
        username: account email.
        password: account password.

    Returns:
        The decoded token dict, annotated with absolute expiry stamps.

    Raises:
        OAuthError: the server rejected the credentials.
        MilaError: transient failure (network, timeout, 5xx, malformed
            body); safe to retry automatically.
    """
    # Standard "Resource Owner Password Credentials" payload per RFC 6749
    # section 4.3. We include `client_id` because Mila's Keycloak is
    # configured to require it even for public clients.
    data = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": username,
        "password": password,
        "scope": SCOPE,
    }
    return await _post_token_request(session, data, "Token request")


async def refresh_token(session: ClientSession, refresh: str) -> Dict[str, Any]:
    """Exchange a refresh token for a new access + refresh token pair.

    Called by `MilaOauthImplementation._async_refresh_token` whenever
    Home Assistant decides the cached access token is about to expire.
    Keycloak rotates the refresh token on each call, so the caller must
    persist the entire returned dict, not just `access_token`.

    Args:
        session: aiohttp client session (shared with Home Assistant).
        refresh: the previously issued `refresh_token` value.

    Returns:
        The decoded token dict, annotated with absolute expiry stamps.

    Raises:
        OAuthError: the refresh token was rejected (revoked, expired,
            or otherwise invalid).
        MilaError: transient failure (network, timeout, 5xx, malformed
            body); safe to retry automatically.
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh,
    }
    return await _post_token_request(session, data, "Token refresh")
