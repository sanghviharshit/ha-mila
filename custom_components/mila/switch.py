"""Support for Mila switch entities."""
from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity

from . import MilaEntity, MilaEntity
from .const import (
    CONF_DEVICES,
    DATA_COORDINATOR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ACCOUNT_SWITCH_TYPES = {
    "house_keeper_mode": [
        "House Keeper Mode",
    ],
    "turn_down_service": [
        "Turn Down Service",
    ],
    "sleep_mode": [
        "Sleep Mode",
    ],
    "whitenoise_mode": [
        "Whitenoise Mode",
    ],
    "quarantine": [
        "Quarantine",
    ],
    "quiet_zone": [
        "Quiet Mode",
    ],

}

DEVICE_SWITCH_TYPES = {
    "sounds_enabled": [
        "Sounds Enabled",
    ],
}

SWITCH_TYPES = {**ACCOUNT_SWITCH_TYPES, **DEVICE_SWITCH_TYPES}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up an Mila sensor entity based on a config entry."""
    entry = hass.data[DOMAIN][entry.entry_id]
    conf_devices = entry[CONF_DEVICES]
    coordinator = entry[DATA_COORDINATOR]

    def get_entities():
        """Get the Mila sensor entities."""
        entities = []

        for device in coordinator.data.devices:
            if device.id in conf_devices:
                for variable in SWITCH_TYPES:
                    if hasattr(coordinator.data, variable) or hasattr(device, variable): # Even though the switches are common for the entire account, adding them per device just the way Mila App shows
                        entities.append(MilaSwitch(coordinator, device.id, variable))

        return entities

    async_add_entities(await hass.async_add_job(get_entities), True)


class MilaSwitch(SwitchEntity, MilaEntity):
    """Representation of an Mila switch entity."""

    def __init__(self, coordinator, device_id, variable):
        """Initialize device."""
        super().__init__(coordinator, device_id=device_id, entity_name=SWITCH_TYPES[variable][0])
        self.device_id = device_id
        self.variable = variable

    @property
    def device_class(self) -> SwitchDeviceClass:
        """Return the class of this entity."""
        return SwitchDeviceClass.SWITCH

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        if self.variable == "sounds_enabled":
            return bool(getattr(self.device, self.variable))
        else:
            return bool(getattr(self.account, self.variable))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if self.variable == "sounds_enabled":
            await self.account.set_sounds_enabled(True)
        else:
            await self.account.set_smart_mode(self.variable, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if self.variable == "sounds_enabled":
            await self.device.set_sounds_enabled(False)
        else:
            await self.account.set_smart_mode(self.variable, False)
        await self.coordinator.async_request_refresh()
