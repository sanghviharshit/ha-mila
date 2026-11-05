import logging
from typing import Optional

from ...const import DOMAIN
from ...devices import MilaAppliance
from ..common import MilaSelect

_LOGGER = logging.getLogger(__name__)

SOUND_MODE_MAPPING = {
    "Enabled": "Enabled",
    "DaytimeOnly": "Daytime Only",
    "Disabled": "Disabled",
}

INV_SOUND_MODE_MAPPING = {v: k for k, v in SOUND_MODE_MAPPING.items()}


class MilaSoundModeSelect(MilaSelect):
    def __init__(
        self, 
        device: MilaAppliance
    ):
        super().__init__(device, "Sound Mode", "mdi:volume-high")
        self._current_option_override: Optional[str] = None
        self.device.add_update_listener(self._update_listener)

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_soundmode".lower()

    @property
    def device(self) -> MilaAppliance:
        return self._device        

    @property
    def current_option(self) -> Optional[str]:
        if self._current_option_override is not None:
            return self._current_option_override
        try:
            val = self.device.get_value("room.soundsConfig")
            if val is None:
                return None
            val_str = getattr(val, "value", str(val))
            return SOUND_MODE_MAPPING.get(val_str)
        except Exception as ex:
            _LOGGER.error(f"Error getting sound mode for {self.name}", exc_info=ex)
            return None

    @property
    def options(self) -> list[str]:
        return list(SOUND_MODE_MAPPING.values())

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            _LOGGER.warning("'%s' is not a valid sound mode option", option)
            return

        self._current_option_override = option
        self.async_write_ha_state()

        sounds_config = INV_SOUND_MODE_MAPPING[option]
        await self.device.set_sound_mode(sounds_config)

    def _update_listener(self) -> None:
        if self._current_option_override is not None:
            try:
                val = self.device.get_value("room.soundsConfig")
                val_str = getattr(val, "value", str(val)) if val else None
                if SOUND_MODE_MAPPING.get(val_str) == self._current_option_override:
                    self._current_option_override = None
            except Exception:
                pass
