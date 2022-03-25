"""Support for Mila Air Quality Monitor (PM2.5)."""
import logging

from homeassistant.components.air_quality import AirQualityEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from . import MilaEntity
from .milacloud import MilaException
from .milacloud.device import Device

from .const import (
    CONF_DEVICE,
    CONF_DEVICES,
    DATA_COORDINATOR,
    DOMAIN,
    MANUFACTURER,
)

_LOGGER = logging.getLogger(__name__)

ATTR_PM_1_0 = "particulate_matter_1_0"
ATTR_TVOC= "total_volatile_organic_compounds"
ATTR_TEMP = "temperature"
ATTR_HUM = "humidity"

PROP_TO_ATTR = {
    "particulate_matter_1_0": ATTR_PM_1_0,
    "total_volatile_organic_compounds": ATTR_TVOC,
    "temperature": ATTR_TEMP,
    "humidity": ATTR_HUM,
}


class MilaAirMonitor(AirQualityEntity, MilaEntity):
    """Air Quality class for Mila Air Purifier device."""

    def __init__(self, coordinator, device_id):
        """Initialize the entity."""
        super().__init__(coordinator, device_id, platform_name="Air Monitor")
        self.coordinator = coordinator
        self.device_id = device_id
        self._icon = "mdi:cloud"

    @property
    def icon(self):
        """Return the icon to use for device if any."""
        return self._icon

    @property
    def air_quality_index(self):
        """Return the Air Quality Index (AQI)."""
        return self.device.aqi

    @property
    def particulate_matter_2_5(self):
        """Return the particulate matter 2.5 level."""
        return self.device.pm_2_5

    @property
    def particulate_matter_10(self):
        """Return the particulate matter 10 level."""
        return self.device.pm_10

    @property
    def particulate_matter_1_0(self):
        """Return the particulate matter 1.0 level."""
        return self.device.pm_1_0

    @property
    def carbon_dioxide(self):
        """Return the CO2 (carbon dioxide) level."""
        return self.device.eco2

    @property
    def carbon_monoxide(self):
        """Return the CO level."""
        return self.device.coppm

    @property
    def total_volatile_organic_compounds(self):
        """Return the total volatile organic compounds."""
        return self.device.tvoc

    @property
    def temperature(self):
        """Return the current temperature."""
        return self.device.temperature

    @property
    def humidity(self):
        """Return the current humidity."""
        return self.device.humidity

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        data = {}

        for prop, attr in PROP_TO_ATTR.items():
            if (value := getattr(self, prop)) is not None:
                data[attr] = value

        return data

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
                entities.append(MilaAirMonitor(coordinator, device.id))

        return entities

    async_add_entities(await hass.async_add_job(get_entities), update_before_add=True)
