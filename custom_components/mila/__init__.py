"""Entry point for the Mila Air Purifier integration.

Home Assistant calls into this module to set up and tear down config
entries. The actual work lives in the data-update coordinator
(`update_coordinator.MilaUpdateCoordinator`); this file only wires
things together and translates exceptions into the error types HA's
config-entry machinery understands.

Exception translation matters because HA reacts differently to each:

* `ConfigEntryAuthFailed`  -> user is shown a reauth flow.
* `ConfigEntryNotReady`    -> HA will retry setup periodically.
* anything else            -> the entry is marked failed and stays failed
                              until the user manually reloads.

We catch broad enough categories here to ensure no aiohttp/Mila exception
ever escapes as a bare `Exception` to HA.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import MilaError, OAuthError
from .const import DOMAIN
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Component-level setup hook.

    Required by Home Assistant for integrations that also support config
    entries. We don't have any YAML-driven configuration, so this is
    just a no-op that returns success.
    """
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bring up a single Mila config entry.

    Steps:
      1. Allocate the per-domain `hass.data` slot if it doesn't exist yet.
      2. Construct the coordinator (which immediately constructs its
         GraphQL client and auth bridge).
      3. Drive the first refresh + forward to platforms via
         `coordinator.async_setup`.
      4. Convert any raised exception into the right HA failure type.
      5. Register an update listener so options changes propagate
         immediately without a full reload.
    """
    # `hass.data[DOMAIN]` is a dict keyed by config-entry id. We may be
    # adding the second or third entry of this integration, so make sure
    # the outer dict exists without clobbering existing entries.
    hass.data.setdefault(DOMAIN, {})

    coordinator = MilaUpdateCoordinator(hass, entry)
    # Store the coordinator before calling `async_setup` so that any
    # cleanup path (including failure) can find it via `hass.data`.
    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        if not await coordinator.async_setup():
            # `async_setup` only returns False after the first refresh
            # succeeds but platform forwarding fails. Close the auth
            # session so we don't leak aiohttp resources.
            await coordinator.async_close_session()
            return False
    except ConfigEntryAuthFailed:
        # The coordinator already translated OAuth failure for us.
        # Don't wrap it again or HA will lose the auth-flow trigger.
        await coordinator.async_close_session()
        raise
    except OAuthError as ex:
        # Raised by `MilaApi` if the token endpoint flat-out rejected us.
        # Promote to HA's reauth signal so the user is prompted to
        # update credentials.
        await coordinator.async_close_session()
        raise ConfigEntryAuthFailed(str(ex)) from ex
    except MilaError as ex:
        # Transient API problem (network blip, 5xx, malformed response).
        # `ConfigEntryNotReady` makes HA retry in a backoff loop.
        await coordinator.async_close_session()
        raise ConfigEntryNotReady(f"Mila API not reachable: {ex}") from ex
    except Exception as ex:
        # Defence in depth: anything not already caught above is logged
        # with a full traceback and then surfaced as NotReady (so HA
        # keeps retrying instead of giving up forever).
        _LOGGER.exception("Unexpected Mila setup failure")
        await coordinator.async_close_session()
        raise ConfigEntryNotReady(str(ex)) from ex

    # Register the options-update listener. `async_on_unload` ties the
    # listener's lifecycle to the entry so we don't leak callbacks when
    # the entry is removed or reloaded.
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down a config entry on user request or reload.

    Delegates the actual unload to the coordinator (which closes the
    auth session and unloads each platform). We only drop the entry
    from `hass.data` if the unload succeeded; otherwise HA might call
    us again with the same entry and we'd want the coordinator to
    still be reachable.
    """
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    ok = await coordinator.async_reset()
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok


async def async_update_options(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Apply options-flow changes to the running coordinator.

    The options flow can change `scan_interval` and `timeout`. We push
    them straight onto the live coordinator (`apply_options`) rather
    than calling `async_reload`, which would tear down every entity and
    recreate it. Only options change here, so a hot apply is safe.
    """
    coordinator: MilaUpdateCoordinator | None = (
        hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    )
    if coordinator is None:
        # Coordinator was already removed (race between unload and
        # options save). Nothing to do.
        return
    coordinator.apply_options(config_entry.options)
