"""Sensor platform: registers every `MilaSensor` produced by a device wrapper.

The shape of every per-platform setup file in this integration is
identical: pull the coordinator out of `hass.data`, ask each device for
its entity list, filter to the relevant base class, and forward to
`async_add_entities`. Sensor is by far the largest list (PM levels,
temperature, humidity, VOC, CO/CO2, AQI, RPM, filter dates, plus all
the location-side sensors).
"""
from __future__ import annotations

import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entities import MilaSensor
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Add every `MilaSensor` instance the coordinator's devices created."""
    _LOGGER.debug("Adding Mila sensors")
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    devices = list(coordinator.devices.values())
    _LOGGER.debug("Found %d devices", len(devices))
    entities = [
        entity
        for device in devices
        for entity in device.entities
        if isinstance(entity, MilaSensor)
    ]
    _LOGGER.debug("Found %d sensors", len(entities))
    async_add_entities(entities)
