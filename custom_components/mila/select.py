"""Mila Select Entities"""
import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entities import MilaSelect
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Callable):
    """Mila selects."""
    _LOGGER.debug('Adding Mila selects')
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    devices = list(coordinator.devices.values())
    _LOGGER.debug(f'Found {len(devices):d} devices')
    entities = [
        entity
        for device in devices
        for entity in device.entities
        if isinstance(entity, MilaSelect)
    ]
    _LOGGER.debug(f'Found {len(entities):d} switches')
    async_add_entities(entities)
