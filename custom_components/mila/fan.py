"""Support for MilaAir Purifier."""
from abc import abstractmethod
import asyncio
from html import entities
import logging
import math

import voluptuous as vol

from homeassistant.components.fan import (
    SUPPORT_PRESET_MODE,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from . import MilaEntity
from .milacloud import MAX_FAN_RPM

# Features
FEATURE_SET_FAVORITE_LEVEL = 16
FEATURE_SET_AUTO_DETECT = 32
FEATURE_SET_EXTRA_FEATURES = 512
FEATURE_SET_FAN_LEVEL = 4096
FEATURE_SET_CLEAN = 16384
FEATURE_SET_DISPLAY = 1048576


FEATURE_FLAGS_AIRPURIFIER = (
    FEATURE_SET_FAN_LEVEL
    | FEATURE_SET_AUTO_DETECT
    | FEATURE_SET_FAVORITE_LEVEL
    | FEATURE_SET_EXTRA_FEATURES
    | FEATURE_SET_CLEAN
    | FEATURE_SET_DISPLAY
)

from .const import (
    CONF_DEVICES,
    DATA_COORDINATOR,
    DOMAIN,
    MANUFACTURER,
    SERVICE_SET_EXTRA_FEATURES,
)
from .milacloud.device import Device

_LOGGER = logging.getLogger(__name__)

# TODO: Add some preset modes
# PRESET_MODES_AIRPURIFIER = [
#     "Auto",
#     "Silent",
#     "Favorite",
#     "Idle",
#     "Medium",
#     "High",
#     "Strong",
# ]

SPEED_MODE_MAPPING = {
    "Off": 0,
    "Silent": 10,
    "Favorite": 10,
    "Idle": 25,
    "Medium": 50,
    "High": 75,
    "Strong": 100,
}

PRESET_AIRPURIFIER_MODES = [
    "automagic",
    "manual",
]

REVERSE_SPEED_MODE_MAPPING = {v: k for k, v in SPEED_MODE_MAPPING.items()}

# Air Purifier
ATTR_FAN_LEVEL = "fan_level"
ATTR_SLEEP_TIME = "sleep_time"
ATTR_EXTRA_FEATURES = "extra_features"
ATTR_FEATURES = "features"
ATTR_TURBO_MODE_SUPPORTED = "turbo_mode_supported"
ATTR_SLEEP_MODE = "sleep_mode"

# Map attributes to properties of the state object
AVAILABLE_ATTRIBUTES_AIRPURIFIER = {
    ATTR_FAN_LEVEL: "fan_level",
    ATTR_EXTRA_FEATURES: "extra_features",
}

AIRPURIFIER_SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.entity_ids})

SERVICE_SCHEMA_EXTRA_FEATURES = AIRPURIFIER_SERVICE_SCHEMA.extend(
    {vol.Required(ATTR_FEATURES): cv.positive_int}
)

SERVICE_TO_METHOD = {
    SERVICE_SET_EXTRA_FEATURES: {
        "method": "async_set_extra_features",
        "schema": SERVICE_SCHEMA_EXTRA_FEATURES,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Mila Air Quality from a config entry."""
    entry = hass.data[DOMAIN][entry.entry_id]
    conf_devices = entry[CONF_DEVICES]
    coordinator = entry[DATA_COORDINATOR]

    def get_entities():
        """Get the Mila sensor entities."""
        entities = []
        for device in coordinator.data.devices:
            if device.id in conf_devices:
                entities.append(MilaAirPurifier(coordinator, device.id))

        return entities

    async_add_entities(await hass.async_add_job(get_entities), update_before_add=True)


class MilaAirPurifier(MilaEntity, FanEntity):
    """Representation of a Mila device."""

    def __init__(self, coordinator, device_id):
        """Initialize the Mila Air Purifier device."""
        super().__init__(
            coordinator, device_id=device_id, platform_name="Air Purifier Fan"
        )

        self.device_id = device_id
        self._state_attrs = {}
        self._device_features = FEATURE_FLAGS_AIRPURIFIER
        self._available_attributes = AVAILABLE_ATTRIBUTES_AIRPURIFIER
        self._preset_modes = PRESET_AIRPURIFIER_MODES
        self._supported_features = SUPPORT_SET_SPEED | SUPPORT_PRESET_MODE
        self._speed_count = 10

    @property
    def is_on(self):
        """Return true if the entity is on."""
        return self.device.is_on

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    @property
    def preset_modes(self) -> list:
        """Get the list of available preset modes."""
        return self._preset_modes

    @property
    def percentage(self):
        """Return the percentage based speed of the fan."""
        return self.device.fan_speed * 100 / MAX_FAN_RPM

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        return self._state_attrs

    @property
    def speed_count(self):
        """Return the number of speeds of the fan supported."""
        return self._speed_count

    @property
    def preset_mode(self):
        """Get the active preset mode."""
        return self.device.fan_mode

    async def async_turn_on(
        self,
        speed: str = None,
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """Turn the device on."""
        # If operation mode was set the device must not be turned on.
        if percentage:
            await self.async_set_percentage(percentage)
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        if percentage is None and preset_mode is None:
            await self.async_set_preset_mode("automagic")

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        await self.async_set_percentage(0)

    # TODO: Convert the pecentage back and forth from how Mila converts RPM to %. (It's uneven distribution of RPM ranges to Percentage)
    async def async_set_percentage(self, percentage: int) -> None:
        """Set the percentage of the fan."""
        await self.async_set_preset_mode("manual")
        await self.device.set_fan_speed(percentage)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode not in self.preset_modes:
            _LOGGER.warning("'%s'is not a valid preset mode", preset_mode)
            return

        _LOGGER.info(f"Setting the fan mode to {preset_mode} speed")
        await self.device.set_fan_mode(preset_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_extra_features(self, features: int = 1):
        """Set the extra features."""
        # self._device.set_extra_features()
