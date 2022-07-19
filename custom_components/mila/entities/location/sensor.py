import logging
from typing import Optional
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass

from ...devices import MilaLocation
from ..common import MilaSensor

_LOGGER = logging.getLogger(__name__)

class MilaLocationSensor(MilaSensor):
    def __init__(
        self, 
        device: MilaLocation, 
        name: str, 
        icon: Optional[str] = None, 
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None
    ):
        super().__init__(device, name, icon, uom, device_class, state_class)

    @property
    def device(self) -> MilaLocation:
        return self._device
