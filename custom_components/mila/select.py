"""Select platform: the sound-mode dropdown per appliance.

Same shape as the other platform files. Currently only one select
entity exists per appliance (`MilaSoundModeSelect`), but the
collection-style code keeps things uniform if Mila ever adds another.
"""
from __future__ import annotations

import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entities import MilaSelect
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Add every `MilaSelect` instance the coordinator's devices created."""
    _LOGGER.debug("Adding Mila selects")
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    devices = list(coordinator.devices.values())
    _LOGGER.debug("Found %d devices", len(devices))
    entities = [
        entity
        for device in devices
        for entity in device.entities
        if isinstance(entity, MilaSelect)
    ]
    _LOGGER.debug("Found %d selects", len(entities))
    async_add_entities(entities)
