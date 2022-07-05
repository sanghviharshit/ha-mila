"""Milacares API"""

import logging
from typing import List
from benedict import benedict
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.sensor import SensorDeviceClass

from milasdk import MilaApi

from ..util import camel_case_split, coalesce
from .device import MilaDevice

_LOGGER = logging.getLogger(__name__)

class MilaLocation(MilaDevice):
    """
    API class to represent a location.
    """    
    def __init__(self, coordinator: DataUpdateCoordinator, api: MilaApi, device_id: str):
        super().__init__(coordinator, api, device_id)

    @property
    def name(self) -> str:
        return f"{self._device_data['address.city']}, \
            {self._device_data['address.country']} \
            (#{self._device_data['id']})"

    @property
    def _device_data(self) -> benedict:
        return self._location_data[self.id]

    def _get_all_entities(self) -> List[Entity]:
        #deal with circular imports by bringing in the sensors here
        from ..entities import (
            MilaLocationAqiSensor,
            MilaLocationPathSensor, 
            MilaLocationDistanceSensor,
            to_pollen_index
        )
        entities = [
            MilaLocationPathSensor(self, "Station Name", "outdoorStation.name", icon="mdi:map-marker"),
            MilaLocationPathSensor(self, "Station Latitude", "outdoorStation.point.lat", icon="mdi:latitude"),
            MilaLocationPathSensor(self, "Station Longitude", "outdoorStation.point.lon", icon="mdi:longitude"),
            MilaLocationPathSensor(self, "Station PM2.5", "outdoorStation.sensor.latest.value", device_class=SensorDeviceClass.PM25, uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            MilaLocationPathSensor(self, "Pollen Station Name", "pollenStation.name", icon="mdi:map-marker"),
            MilaLocationPathSensor(self, "Pollen Reported Date", "pollenStation.aggregateWindow[-1].date", device_class=SensorDeviceClass.DATE),
            MilaLocationPathSensor(self, "Pollen Status - Trees", "pollenStation.aggregateWindow[-1].status.trees", icon="mdi:tree"),
            MilaLocationPathSensor(self, "Pollen Status - Weeds", "pollenStation.aggregateWindow[-1].status.weeds", icon="mdi:flower"),
            MilaLocationPathSensor(self, "Pollen Status - Grass", "pollenStation.aggregateWindow[-1].status.grass", icon="mdi:grass"),
            MilaLocationPathSensor(self, "Pollen Status - Mold", "pollenStation.aggregateWindow[-1].status.mold", icon="mdi:mushroom"),

            MilaLocationAqiSensor(self),
            MilaLocationDistanceSensor(self),
        ]

        return entities

