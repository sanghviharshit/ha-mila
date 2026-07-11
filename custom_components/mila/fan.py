"""Fan platform: registers `MilaFan` entities and the `set_bedtime` service.

Home Assistant calls `async_setup_entry` once per config entry when the
fan platform is forwarded. We iterate the coordinator's per-device
wrappers, filter to ones that produced a `MilaFan` entity, and hand
them to HA via `async_add_entities`.

The platform also registers the integration-level `mila.set_bedtime`
service. We do it here (rather than in `__init__.py`) because the
service is entity-targeted: HA needs a platform instance in scope to
register a per-entity service handler.
"""
from __future__ import annotations

import logging
from typing import Callable

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform

from .const import DOMAIN
from .entities import MilaFan
from .update_coordinator import MilaUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Service name as it appears in `services.yaml`; also what users type
# into automations / scripts (`mila.set_bedtime`).
SERVICE_SET_BEDTIME = "set_bedtime"

# Schema for the service call payload. `cv.time` accepts either
# "HH:MM" or "HH:MM:SS" and returns a `datetime.time` instance, which
# the entity's `async_set_bedtime` then `.isoformat()`s into the
# server's `LocalTime` format.
SET_BEDTIME_SCHEMA = {
    vol.Required("local_start"): cv.time,
    vol.Required("local_end"): cv.time,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Register Mila fan entities and the per-entity bedtime service."""
    _LOGGER.debug("Adding Mila fans")
    # The coordinator was created and stored in `__init__.async_setup_entry`.
    # By the time the fan platform is forwarded, `coordinator.devices`
    # has already been populated (the first refresh happened during
    # `coordinator.async_setup`).
    coordinator: MilaUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    devices = list(coordinator.devices.values())
    _LOGGER.debug("Found %d devices", len(devices))

    # Each device wrapper exposes a flat list of HA `Entity` objects.
    # We pick only the ones that are fans for this platform; sensor,
    # switch, and select platforms do the analogous filtering against
    # their own base classes.
    entities = [
        entity
        for device in devices
        for entity in device.entities
        if isinstance(entity, MilaFan)
    ]
    _LOGGER.debug("Found %d fans", len(entities))
    async_add_entities(entities)

    # Register `mila.set_bedtime` as an entity-targeted service. The
    # last argument is the *method name* on the entity that HA should
    # call; `MilaApplianceFan.async_set_bedtime` does the actual work.
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_BEDTIME,
        SET_BEDTIME_SCHEMA,
        "async_set_bedtime",
    )
