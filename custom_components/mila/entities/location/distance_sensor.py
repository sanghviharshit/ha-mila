from geopy.distance import geodesic

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

class MilaLocationDistanceSensor(MilaLocationSensor):
    def __init__(
        self, 
        device: MilaLocation
    ):
        super().__init__(device, "Station Distance", "mdi:map-marker-distance", uom="km")

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_distance".lower()  

    @property
    def native_value(self):
        location_point = (float(self.device.get_value("address.point.lat")),
            float(self.device.get_value("address.point.lon")))
        station_point = (float(self.device.get_value("outdoorStation.point.lat")),
            float(self.device.get_value("outdoorStation.point.lon")))

        return round(geodesic(location_point, station_point).km,2)
