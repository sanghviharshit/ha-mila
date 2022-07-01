import logging
from typing import Optional
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

_LOGGER = logging.getLogger(__name__)

class MilaLocationPathSensor(MilaLocationSensor):
    def __init__(
        self, 
        device: MilaLocation, 
        name: str, 
        data_path: str, 
        icon: Optional[str] = None, 
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
        convert_function = None
    ):
        super().__init__(device, name, icon, uom, device_class, state_class)
        self._data_path = data_path
        self._convert_function = convert_function

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_{self._data_path.replace('.','_')}".lower()

    @property
    def native_value(self):
        try:
            val = self.device.get_value(self._data_path)
            if self._convert_function is not None:
                val = self._convert_function(val)
            return val
        except KeyError:
            return None
        except Exception as ex:
            _LOGGER.error(f"Error getting native value for {self.name}", exc_info=ex)
            return None
