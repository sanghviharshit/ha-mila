import aqi
from homeassistant.components.sensor import SensorDeviceClass

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

class MilaLocationAqiSensor(MilaLocationSensor):
    def __init__(
        self, 
        device: MilaLocation
    ):
        super().__init__(device, "AQI", device_class=SensorDeviceClass.AQI)

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_aqi".lower()  

    @property
    def native_value(self):
        pm25: float = self.device.get_value("outdoorStation.sensor.latest.value")
        return aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm25), algo=aqi.ALGO_EPA)
