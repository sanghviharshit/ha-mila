from typing import Any, Optional
from homeassistant.components.select import SelectEntity

from ...devices import MilaDevice
from .entity import MilaEntity

class MilaSelect(MilaEntity, SelectEntity):
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

    @property
    def options(self) -> list[str]:
        raise NotImplementedError

    @property
    def current_option(self) -> Optional[str]:
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        raise NotImplementedError