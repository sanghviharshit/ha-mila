"""Support for Mila sensor entities."""
from collections.abc import Mapping
import logging
from typing import Any, final

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass, SensorEntity
from homeassistant.const import (
    PERCENTAGE, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, TEMP_CELSIUS,
    CONCENTRATION_PARTS_PER_MILLION, CONCENTRATION_PARTS_PER_BILLION
)
from homeassistant.helpers.typing import StateType

from . import MilaEntity
from .const import (
    CONF_DEVICES,
    DATA_COORDINATOR,
    DOMAIN,
)
from .util import format_data_usage

_LOGGER = logging.getLogger(__name__)

BASIC_TYPES = {
    # TODO: Move these to binary sensors
    # "quiet_enabled": [
    #     "Quite Enabled",
    #     None,
    #     None,
    # ],
    # "night_enabled": [
    #     "Night Enabled",
    #     None,
    #     None,
    # ],
    # "housekeeper_enabled": [
    #     "Housekeeper Enabled",
    #     None,
    #     None,
    # ],
    # "quarantine_enabled": [
    #     "Quarantine Enabled",
    #     None,
    #     None,
    # ],
    # "sleep_enabled": [
    #     "Sleep Enabled",
    #     None,
    #     None,
    # ],
    # "turndown_enabled": [
    #     "Turndown Enabled",
    #     None,
    #     None,
    # ],
    # "whitenoise_enabled": [
    #     "Whitenoise Enabled",
    #     None,
    #     None,
    # ],
    # "sounds_enabled": [
    #     "Sounds Enabled",
    #     None,
    #     None,
    # ],
    # TODO: Move these to allow user override
    # "local_night_start": [
    #     "Night Start Time",
    #     None,
    #     None,
    # ],
    # "local_night_end": [
    #     "Night End Time",
    #     None,
    #     None,
    # ],
    # TODO: Move these as attributes for fan entity
    # "sleep_fan_mode": [
    #     "Sleep Fan Mode",
    #     None,
    #     None,
    # ],
    # "turndown_fan_mode": [
    #     "Turndown Fan Mode",
    #     None,
    #     None,
    # ],
    # "whitenoise_fan_mode": [
    #     "Whitenoise Fan Mode",
    #     None,
    #     None,
    # ],
}

SENSOR_TYPES = {
    "aqi": [
        "AQI",
        SensorDeviceClass.AQI,
        "AQI",
        SensorStateClass.MEASUREMENT,
    ],
    "pm_1_0": [
        "PM 1.0",
        SensorDeviceClass.PM1,
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        SensorStateClass.MEASUREMENT,
    ],
    "pm_2_5": [
        "PM 2.5",
        SensorDeviceClass.PM25,
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        SensorStateClass.MEASUREMENT,
    ],
    "pm_10": [
        "PM 10",
        SensorDeviceClass.PM10,
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        SensorStateClass.MEASUREMENT,
    ],
    "coppm": [
        "CO",
        SensorDeviceClass.CO,
        CONCENTRATION_PARTS_PER_MILLION,
        SensorStateClass.MEASUREMENT,
    ],
    "eco2": [
        "CO2",
        SensorDeviceClass.CO2,
        CONCENTRATION_PARTS_PER_MILLION,
        SensorStateClass.MEASUREMENT,
    ],
    "tvoc": [
        "VOC",
        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        CONCENTRATION_PARTS_PER_BILLION,
        SensorStateClass.MEASUREMENT,
    ],
    "temperature": [
        "Temperature",
        SensorDeviceClass.TEMPERATURE,
        TEMP_CELSIUS,
        SensorStateClass.MEASUREMENT,
    ],
    "humidity": [
        "Humidity",
        SensorDeviceClass.HUMIDITY,
        PERCENTAGE,
        SensorStateClass.MEASUREMENT,
    ],
}


SENSOR_TYPES = {**BASIC_TYPES, **SENSOR_TYPES}

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
                for variable in SENSOR_TYPES:
                    if hasattr(device, variable):
                        entities.append(MilaSensor(coordinator, device.id, variable))

        return entities

    async_add_entities(await hass.async_add_job(get_entities), True)


class MilaSensor(SensorEntity, MilaEntity):
    """Representation of an Mila sensor entity."""

    def __init__(self, coordinator, device_id, variable):
        """Initialize device."""
        super().__init__(coordinator, device_id=device_id, entity_name=SENSOR_TYPES[variable][0])
        self.device_id = device_id
        self.variable = variable

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the class of this entity."""
        return SENSOR_TYPES[self.variable][1]

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class of this entity, if any."""
        return SENSOR_TYPES[self.variable][3]

    @property
    def state(self) -> StateType:
        """Return the state of the entity."""
        return getattr(self.device, self.variable)

    @final
    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the entity, after unit conversion."""
        return SENSOR_TYPES[self.variable][2]

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.device.id}-{self.variable}"
