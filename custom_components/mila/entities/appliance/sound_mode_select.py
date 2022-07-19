import logging
from typing import Any, Optional
from milasdk import SoundsConfig

from ...const import DOMAIN
from ...devices import MilaAppliance
from ..common import MilaSelect
from ...util import camel_case_split

_LOGGER = logging.getLogger(__name__)

MODE_MAPPING = {}
for m in SoundsConfig:
    MODE_MAPPING[m] = ' '.join(camel_case_split(m.value))

INV_MODE_MAPPING = {v: k for k, v in MODE_MAPPING.items()}    

class MilaSoundModeSelect(MilaSelect):
    def __init__(
        self, 
        device: MilaAppliance
    ):
        super().__init__(device, "Sound Mode", "mdi:volume-high")

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_soundmode".lower()

    @property
    def device(self) -> MilaAppliance:
        return self._device        

    @property
    def current_option(self) -> Optional[str]:
        try:
            return self.device.get_value("room.soundsConfig")
        except Exception as ex:
            _LOGGER.error(f"Error getting sound mode for {self.name}", exc_info=ex)
            return None

    @property
    def options(self) -> list[str]:
        return list(MODE_MAPPING.values())

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            _LOGGER.warning("'%s'is not a valid select option", option)
            return
        
        await self.device.set_sound_mode(INV_MODE_MAPPING[option])
