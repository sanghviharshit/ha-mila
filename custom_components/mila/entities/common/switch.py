from typing import Any, Optional
from homeassistant.components.switch import SwitchEntity

from ...devices import MilaDevice
from .entity import MilaEntity

class MilaSwitch(MilaEntity, SwitchEntity):
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
    def is_on(self) -> bool:
        """Return True if entity is on."""
        raise NotImplementedError
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        raise NotImplementedError

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""    
        raise NotImplementedError