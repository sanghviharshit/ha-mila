"""Milacares API"""

from benedict import benedict
from typing import List
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CALLBACK_TYPE
from milasdk import MilaApi

from ..const import DATAKEY_ACCOUNT, DATAKEY_APPLIANCE, DATAKEY_LOCATION, DOMAIN, MANUFACTURER

class MilaDevice():
    """
    API class to represent a single device.

    Since a physical device can have many entities, we'll pool common elements here
    """    
    def __init__(self, coordinator: DataUpdateCoordinator, api: MilaApi, device_id: str):
        self._id = device_id
        self._hass = coordinator.hass
        self._coordinator = coordinator
        self._api = api
        self._entities = {}
        self._build_entities_list()

    @property
    def hass(self) -> HomeAssistant:
        return self._hass

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return True

    @property
    def name_or_id(self) -> str:
        return self.name if self.name is not None else self.id

    @property
    def entities(self) -> list[Entity]:
        return list(self._entities.values())

    @property
    def device_info(self) -> DeviceInfo:
        """
        Return device specific attributes.
        """
        name = self.name
        model = "Mila Air Purifier"
        sw_version = self._get_software_version()

        return DeviceInfo(
            identifiers= {(DOMAIN, self.id)},
            manufacturer= MANUFACTURER,
            model=model,
            name=name,
            sw_version=sw_version
        )

    @property
    def _appliance_data(self) -> benedict:
        return benedict(self._coordinator.data.get(DATAKEY_APPLIANCE,{}))

    @property
    def _account_data(self) -> benedict:
        return benedict(self._coordinator.data.get(DATAKEY_ACCOUNT,{}))

    @property
    def _location_data(self) -> benedict:
        return benedict(self._coordinator.data.get(DATAKEY_LOCATION,{}))

    @property
    def _device_data(self) -> benedict:
        raise NotImplementedError

    def get_value(self, data_path: str):
        return self._device_data[data_path]

    def add_update_listener(self, callback: CALLBACK_TYPE):
        self._coordinator.async_add_listener(callback)

    def _build_entities_list(self) -> dict[str, Entity]:
        """Build the entities list, adding anything new."""
        from ..entities import MilaEntity
        entities = [
            e for e in self._get_all_entities()
            if isinstance(e, MilaEntity)
        ]

        for entity in entities:
            if entity.unique_id not in self._entities:
                self._entities[entity.unique_id] = entity        

    def _get_all_entities(self) -> List[Entity]:
        return []

    def _get_software_version(self) -> str:
        return ""
