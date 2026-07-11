"""Data update coordinator: single poll, all Mila state.

`DataUpdateCoordinator` is the Home Assistant primitive for "poll this
remote API on a schedule and notify entities when fresh data arrives."
Every Mila entity reads from the cached data this coordinator produces;
none of them talk to the API directly.

The design choices here are:

* **One coordinator per config entry.** Multiple accounts -> multiple
  coordinators. Each owns its own `MilaApi` instance.

* **One round trip per refresh.** The `GET_APPLIANCES` query returns
  every per-appliance field we need (smart modes, performance config,
  sensors, room metadata, filter info, current state) in one go, so we
  don't fan out N queries for N appliances.

* **Devices live as long as the coordinator does.** We construct
  `MilaDevice` instances exactly once, on the first refresh. New
  appliances appearing on the account later are *detected* but the
  user has to reload the integration to surface them (because adding
  entities at runtime would require platform-specific machinery we
  don't otherwise need).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_TIMEOUT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import MilaApi, MilaClient, MilaError, OAuthError
from .auth import MilaConfigEntryAuth, MilaOauthImplementation
from .const import (
    DATAKEY_ACCOUNT,
    DATAKEY_APPLIANCE,
    DATAKEY_LOCATION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .devices import MilaAppliance, MilaDevice, MilaLocation

# Platforms we forward to. Each value matches a `<name>.py` file at the
# integration's root that defines `async_setup_entry`.
PLATFORMS = ["sensor", "switch", "fan", "select"]

_LOGGER = logging.getLogger(__name__)


class MilaUpdateCoordinator(DataUpdateCoordinator):
    """Poll the Mila API, cache results, hold the per-account device list.

    Stored under `hass.data[DOMAIN][entry.entry_id]` so platforms and
    services can reach it during their own setup.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Build the auth bridge, GraphQL client, and API facade.

        This constructor is deliberately cheap: no network I/O happens
        until `async_setup` is awaited. That lets `async_setup_entry`
        store us in `hass.data` *before* the first refresh, so any
        failure path can still find us and trigger cleanup.
        """
        self._hass = hass
        self._config_entry = config_entry

        # Read configurable tunables out of `entry.options` first so the
        # client below can be constructed with the user's timeout.
        # Options are set by the options flow; if the user hasn't
        # visited it yet, the defaults from `const.py` apply.
        options = config_entry.options
        self._timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

        # Order matters: implementation -> auth wrapper -> client -> API.
        # The implementation holds credentials; the auth wrapper provides
        # the `async_get_access_token` callable that the client treats as
        # a TokenProvider (plus the unconditional-refresh hook used after
        # a 401); the client knows how to POST to GraphQL; and MilaApi is
        # the high-level convenience layer everything else uses.
        oauth_impl = MilaOauthImplementation(hass, config_entry)
        self._auth = MilaConfigEntryAuth(hass, config_entry, oauth_impl)
        self._client = MilaClient(
            aiohttp_client.async_get_clientsession(hass),
            self._auth.async_get_access_token,
            token_refresher=self._auth.async_force_refresh_token,
            request_timeout=self._timeout,
        )
        self._api = MilaApi(self._client)

        # `_initialized` flips to True after the first successful refresh.
        # Several methods (e.g. `_async_update_data`) check it to decide
        # whether to do one-shot work like building devices.
        self._initialized = False

        # Per-device wrappers keyed by appliance id or "loc_<location_id>".
        # Populated by `_build_devices` on the first refresh; platforms
        # iterate this dict when forming their entity lists.
        self.devices: dict[str, MilaDevice] = {}

        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        # Pass `update_interval` so HA's coordinator schedules our
        # `_async_update_data` automatically. The "name" appears in
        # debug logs to disambiguate multiple coordinators.
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    def apply_options(self, options: Mapping[str, Any]) -> None:
        """Reflect a save from the options flow into the live coordinator.

        Updates `_timeout` immediately (used by the very next refresh)
        and adjusts the base class's `update_interval` so subsequent
        polls run at the new cadence. Avoids the heavier path of fully
        reloading the integration when nothing else changed.
        """
        self._timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        # Keep the client's per-request cap in sync so write paths (fan
        # speed, smart modes) honour the new value too, not just the
        # coordinator-wrapped reads.
        self._client.request_timeout = self._timeout
        new_delta = timedelta(
            seconds=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        # Only assign when the value actually changed so HA doesn't
        # cancel and reschedule the timer pointlessly.
        if self.update_interval != new_delta:
            self.update_interval = new_delta

    async def async_setup(self) -> None:
        """Run the first refresh and forward setup to entity platforms.

        Called from `__init__.async_setup_entry`. The first refresh
        primes `self.data` (which platforms inspect to decide their
        entities) and also flips `_initialized` to True so subsequent
        refreshes know they don't need to rebuild devices.

        Success returns normally; any failure raises, and the caller
        translates the exception into the right `ConfigEntry*` failure
        type. There is deliberately no boolean return: a False that no
        code path could produce invites dead handling upstream.
        """
        _LOGGER.debug("Setting up coordinator")
        # The "first refresh" helper differs from a regular refresh in
        # that it raises `ConfigEntryNotReady` if the first poll fails,
        # which makes HA retry the entire setup later.
        await self.async_config_entry_first_refresh()
        self._initialized = True
        _LOGGER.debug("Forwarding setup to platforms")
        await self.hass.config_entries.async_forward_entry_setups(
            self._config_entry, PLATFORMS
        )

    async def async_reset(self) -> bool:
        """Tear the coordinator down on unload or reload.

        Closes the auth session before unloading platforms; either order
        works for correctness, but closing auth first means in-flight
        platform shutdown can't sneak a final request through after we
        think we've cleaned up.
        """
        _LOGGER.debug("resetting the coordinator")
        await self.async_close_session()
        return await self.hass.config_entries.async_unload_platforms(
            self._config_entry, PLATFORMS
        )

    async def async_close_session(self) -> None:
        """Best-effort cleanup of the auth side-channel.

        Currently a no-op because `MilaOauthImplementation.async_close`
        is itself a no-op (we share HA's aiohttp session). Kept as a
        method so future cleanup work has an obvious place to live.
        """
        if self._auth is None:
            return
        try:
            await self._auth.async_close()
        except Exception as ex:
            # Log but do not raise: cleanup failures shouldn't block the
            # unload path or HA might not be able to re-add the entry.
            _LOGGER.warning("Error closing Mila auth session: %s", ex)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch one full snapshot of API state.

        Called by `DataUpdateCoordinator` on the schedule we set in
        `__init__`. The result becomes `self.data` and triggers
        callbacks on every coordinator listener (every entity).

        Each API call gets its own `asyncio.timeout` block so a hung
        request can be cancelled cleanly without dragging the others
        down with it. (Stdlib `asyncio.timeout` rather than the
        third-party `async_timeout` package: HA no longer guarantees
        the latter is installed, and importing it made the whole
        integration fail to load on clean modern installs.)
        """
        try:
            data: dict[str, Any] = {}

            # On a refresh, we want to compare the old appliance set
            # against the new one so we can log when a device appears.
            # First-refresh has no `self.data` yet, so default to [].
            existing_appliances: list[str] = (
                list(self.data.get(DATAKEY_APPLIANCE, {}).keys())
                if self.data is not None
                else []
            )

            # The owner profile rarely changes (email + name). Fetch it
            # once, on the first refresh, then carry the cached copy
            # forward on every later poll. Without the carry-forward,
            # the second refresh would silently drop the account data
            # (each refresh builds a brand-new `data` dict) and
            # `MilaDevice._account_data` would read empty forever after.
            if not self._initialized:
                async with asyncio.timeout(self._timeout):
                    data[DATAKEY_ACCOUNT] = await self._api.get_account()
            else:
                data[DATAKEY_ACCOUNT] = (self.data or {}).get(DATAKEY_ACCOUNT)

            async with asyncio.timeout(self._timeout):
                appliances = await self._api.get_appliances()
            # Index by id so device wrappers can look up their own data
            # via dotted-path benedict access in O(1).
            data[DATAKEY_APPLIANCE] = {a["id"]: a for a in appliances}

            async with asyncio.timeout(self._timeout):
                locations = await self._api.get_location_data()
            # Location IDs collide with appliance IDs (both integers in
            # general), so prefix with "loc_" when keying for the
            # combined `devices` dict.
            data[DATAKEY_LOCATION] = {
                f"loc_{loc['id']}": loc for loc in locations
            }

            # Build the per-device wrappers on first run only. On later
            # refreshes we just compare to detect newly added devices.
            if not self._initialized:
                await self._build_devices(data)
            else:
                await self._detect_new_devices(
                    existing_appliances, data[DATAKEY_APPLIANCE]
                )

            return data
        except OAuthError as ex:
            # Token is unrecoverable. Promote to HA's reauth signal so
            # the user sees a "Reauthenticate" button on the integration
            # card.
            raise ConfigEntryAuthFailed(str(ex)) from ex
        except MilaError as err:
            # Transient API error (5xx, malformed response). HA will
            # mark the data as stale and retry on the next schedule.
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except asyncio.TimeoutError as err:
            # Our asyncio.timeout fired. Same handling as MilaError but
            # the message tells the user the timeout value to help them
            # diagnose / tune via the options flow.
            raise UpdateFailed(
                f"Timed out talking to Mila API after {self._timeout}s"
            ) from err

    async def _build_devices(self, data: dict[str, Any]) -> None:
        """Create per-device wrappers exactly once, on first refresh.

        Each wrapper builds its own list of entities lazily inside
        `_get_all_entities`; the platforms read those lists in
        `async_setup_entry` to register them with HA.
        """
        for appliance_id in data[DATAKEY_APPLIANCE]:
            _LOGGER.info(
                "Found Mila device with id=%s, setting up...", appliance_id
            )
            self.devices[appliance_id] = MilaAppliance(
                self, self._api, appliance_id
            )
        for location_id in data[DATAKEY_LOCATION]:
            _LOGGER.info(
                "Found Mila location with id=%s, setting up...", location_id
            )
            self.devices[location_id] = MilaLocation(
                self, self._api, location_id
            )

    async def _detect_new_devices(
        self, old: list[str], new: dict[str, Any]
    ) -> None:
        """Log when an appliance shows up that wasn't here last time.

        We don't auto-add the entities for the new device because
        that requires a fresh `async_forward_entry_setups` call and a
        bit of refactoring; the cheaper path is to ask the user to
        reload the integration manually.
        """
        for appliance_id in set(new) - set(old):
            _LOGGER.info(
                "New device with id=%s detected, reload the Mila integration to "
                "expose it in Home Assistant",
                appliance_id,
            )
