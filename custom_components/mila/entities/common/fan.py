from typing import Optional
from homeassistant.components.fan import FanEntity

from ...devices import MilaDevice
from .entity import MilaEntity

class MilaFan(MilaEntity, FanEntity):
    def __init__(
        self, 
        device: MilaDevice, 
        name: str, 
        icon: Optional[str] = None
    ):
        super().__init__(device)
        self._name = name
        self._attr_icon = icon

    @property
    def unique_id(self) -> str:
        raise NotImplementedError
    
    @property
    def name(self) -> str:
        return f"{self.device.name_or_id} {self._name}"

