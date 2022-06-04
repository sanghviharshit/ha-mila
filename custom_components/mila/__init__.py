"""Support for Milacares Air Purifier."""
import async_timeout
from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_MODE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_EMAIL,
    CONF_PASSWORD,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .milacloud.account import Account

from .milacloud.device import Device
from .milacloud.resource import Resource
from .util import snake_case

# from .util import validate_time_format

from .milacloud import MilaAPI, MilaException
from .const import (
    ATTRIBUTION,
    CONF_NAME,
    CONF_SAVE_RESPONSES,
    CONF_TIMEOUT,
    CONF_USER_TOKEN,
    DATA_COORDINATOR,
    DEFAULT_SAVE_LOCATION,
    DEFAULT_SAVE_RESPONSES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MANUFACTURER,
    UNDO_UPDATE_LISTENER,
    CONF_DEVICES,
    DOMAIN,
)

POLLING_TIMEOUT_SEC = 10
UPDATE_INTERVAL = timedelta(seconds=15)

FAN_PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

PLATFORMS = [Platform.AIR_QUALITY, Platform.SENSOR, Platform.FAN, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up a config entry."""
    data = entry.data
    options = entry.options

    conf_devices = options.get(CONF_DEVICES, data[CONF_DEVICES])
    conf_identifiers = [(DOMAIN, resource_id) for resource_id in conf_devices]

    device_registry = hass.helpers.device_registry.async_get(hass)
    for device_entry in hass.helpers.device_registry.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if all(
            [
                bool(resource_id not in conf_identifiers)
                for resource_id in device_entry.identifiers
            ]
        ):
            device_registry.async_remove_device(device_entry.id)

    conf_save_responses = options.get(CONF_SAVE_RESPONSES, DEFAULT_SAVE_RESPONSES)
    conf_scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    conf_timeout = options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

    conf_save_location = DEFAULT_SAVE_LOCATION if conf_save_responses else None

    api = MilaAPI(
        username=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        timeout=conf_timeout,
        save_location=conf_save_location,
        access_token=data[CONF_USER_TOKEN],
        session=hass.helpers.aiohttp_client.async_get_clientsession(),
    )

    async def async_update_data():
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            return await api.update()
        except MilaException as exception:
            raise UpdateFailed(
                f"Error communicating with API: {exception.error_message}"
            ) from exception

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Mila ({data[CONF_NAME]})",
        update_method=async_update_data,
        update_interval=timedelta(seconds=conf_scan_interval),
    )
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_DEVICES: conf_devices,
        DATA_COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: entry.add_update_listener(async_update_listener),
    }

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class MilaEntity(CoordinatorEntity):
    """Representation of a Mila entity."""

    def __init__(
        self, coordinator, device_id, platform_name="Air Purifier", entity_name=None
    ):
        """Initialize device."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.entity_name = entity_name
        self.platform_name = platform_name
        self.platform_name_snake_case = snake_case(platform_name)

    @property
    def device(self) -> Device:
        """Return the state attributes."""
        for device in self.coordinator.data.devices:
            if device.id == self.device_id:
                return device

    @property
    def account(self) -> Account:
        """Return the state attributes."""
        return self.coordinator.data

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if self.entity_name:
            return f"{self.device.name} {self.platform_name} {self.entity_name}"
        return f"{self.device.name} {self.platform_name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        if self.entity_name:
            return (
                f"{self.device.id}-{self.platform_name_snake_case}-{self.entity_name}"
            )
        return f"{self.device.id}-{self.platform_name_snake_case}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes.

        Implemented by platform classes.
        """
        name = f"{self.device.name} Air Purifier"
        model = "Mila Air Purifier"

        sw_version, via_device = None, None
        sw_version = self.device.os_version
        via_device = (DOMAIN, self.device.id)

        return DeviceInfo(
            identifiers={(DOMAIN, self.device.id)},
            manufacturer=MANUFACTURER,
            model=model,
            name=name,
            sw_version=sw_version,
            via_device=via_device,
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return entity specific state attributes.

        Implemented by platform classes. Convention for attribute names
        is lowercase snake_case.
        """
        return {}

    @property
    def attribution(self) -> str:
        """Return the attribution."""
        return ATTRIBUTION
