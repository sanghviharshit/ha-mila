import logging
from typing import Any, Optional
from milasdk import SmartModeKind

from ...const import DOMAIN
from ...devices import MilaAppliance
from ..common import MilaSwitch

_LOGGER = logging.getLogger(__name__)

MODE_MAPPING = {}
for m in SmartModeKind: # map to camelCase
    MODE_MAPPING[m] = ''.join([m.value[0].lower(), m.value[1:]])

class MilaSmartModeSwitch(MilaSwitch):
    def __init__(
        self, 
        device: MilaAppliance, 
        name: str,
        smartmode_kind: SmartModeKind,
        icon: Optional[str] = None
    ):
        super().__init__(device, name, icon)
        self._smartmode_kind = smartmode_kind

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_smartmode_{self._smartmode_kind}".lower()

    @property
    def device(self) -> MilaAppliance:
        return self._device        

    @property
    def is_on(self) -> bool:
        try:
            modes: dict[str, Any] = self.device.get_value("smartModes")
            return modes[MODE_MAPPING[self._smartmode_kind]]["isEnabled"]
        except Exception as ex:
            _LOGGER.error(f"Error getting switch state for {self.name}", exc_info=ex)
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.device.set_smart_mode(self._smartmode_kind, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device.set_smart_mode(self._smartmode_kind, False)