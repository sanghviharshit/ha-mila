from typing import Optional
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass

from ...devices import MilaDevice
from .entity import MilaEntity

class MilaSensor(MilaEntity, SensorEntity):
    def __init__(
        self, 
        device: MilaDevice, 
        name: str, 
        icon: Optional[str] = None, 
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None
    ):
        super().__init__(device)
        self._name = name
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = uom
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def unique_id(self) -> str:
        raise NotImplementedError
    
    @property
    def name(self) -> str:
        return f"{self.device.name_or_id} {self._name}"

    @property
    def native_value(self):
        raise NotImplementedError
