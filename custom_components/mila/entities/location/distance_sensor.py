from geopy.distance import geodesic
from typing import Optional

from homeassistant.const import (
    LENGTH_KILOMETERS,
    LENGTH_MILES
)
from homeassistant.util.unit_system import METRIC_SYSTEM
from homeassistant.util.distance import convert as distance_convert

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

class MilaLocationDistanceSensor(MilaLocationSensor):
    def __init__(
        self, 
        device: MilaLocation
    ):
        super().__init__(device, "Station Distance", "mdi:map-marker-distance")

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_distance".lower()  

    @property
    def native_value(self):
        location_point = (float(self.device.get_value("address.point.lat")),
            float(self.device.get_value("address.point.lon")))
        station_point = (float(self.device.get_value("outdoorStation.point.lat")),
            float(self.device.get_value("outdoorStation.point.lon")))

        val = geodesic(location_point, station_point).km
        if self._is_metric:
            val = distance_convert(val, LENGTH_KILOMETERS, LENGTH_MILES)

        return round(val,2)

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        return LENGTH_KILOMETERS if self._is_metric else LENGTH_MILES

    @property
    def _is_metric(self) -> bool:
        return self.device.hass.config.units is METRIC_SYSTEM