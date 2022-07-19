from typing import Any, Dict, Optional
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from ...devices import MilaDevice

class MilaEntity(CoordinatorEntity):
    """Base class for all Mila entities"""
    def __init__(self, device: MilaDevice):
        super().__init__(device._coordinator)
        self._device = device

    @property
    def device(self) -> MilaDevice:
        return self._device

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self.device.device_info

    @property
    def unique_id(self) -> str:
        raise NotImplementedError        

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return self.device.available