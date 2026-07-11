"""Switch platform: smart-mode toggles per appliance.

See the comment in `sensor.py` for the rationale behind the identical
shape; every platform file is just a filter against the coordinator's
device entity lists. Switch covers the smart-mode toggles (Quiet,
Quarantine, Child Lock, Housekeeper, Sleep, Turndown, Whitenoise).
"""
from __future__ import annotations

import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entities import MilaSwitch
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Add every `MilaSwitch` instance the coordinator's devices created."""
    _LOGGER.debug("Adding Mila switches")
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    devices = list(coordinator.devices.values())
    _LOGGER.debug("Found %d devices", len(devices))
    entities = [
        entity
        for device in devices
        for entity in device.entities
        if isinstance(entity, MilaSwitch)
    ]
    _LOGGER.debug("Found %d switches", len(entities))
    async_add_entities(entities)
