"""Support for Milacares Air Purifier."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the ge_home component."""
    hass.data.setdefault(DOMAIN, {})

    """Set up ge_home from a config entry."""
    coordinator = MilaUpdateCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        if not await coordinator.async_setup():
            # Setup returned False, close session to prevent leak
            await coordinator.async_close_session()
            return False
    except Exception as ex:
        # Setup failed with exception, close session to prevent leak
        _LOGGER.error(f"Mila setup failed: {ex}")
        await coordinator.async_close_session()
        raise

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    ok = await coordinator.async_reset()
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return ok

async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry):
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)
