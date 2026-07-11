"""The sound-mode dropdown entity, one per appliance.

The Mila API stores the sound mode as a `SoundsConfig` enum value
(`Enabled` / `DaytimeOnly` / `Disabled`). We present the same three
options to users but with the camel-case names split into separate
words ("Daytime Only" reads better than "DaytimeOnly"). The
`MODE_MAPPING` and its inverse handle the two-way translation.
"""
from __future__ import annotations

import logging
from typing import Optional

from ...api import SoundsConfig
from ...const import DOMAIN
from ...devices import MilaAppliance
from ...util import camel_case_split
from ..common import MilaSelect

_LOGGER = logging.getLogger(__name__)


# Enum member -> human label, built once at import time.
#
#   SoundsConfig.Enabled      -> "Enabled"
#   SoundsConfig.DaytimeOnly  -> "Daytime Only"
#   SoundsConfig.Disabled     -> "Disabled"
MODE_MAPPING: dict[SoundsConfig, str] = {
    m: " ".join(camel_case_split(m.value)) for m in SoundsConfig
}
# Inverse map used to translate the user's selection back to the enum
# member before sending it to the API.
INV_MODE_MAPPING: dict[str, SoundsConfig] = {v: k for k, v in MODE_MAPPING.items()}


class MilaSoundModeSelect(MilaSelect):
    """Dropdown for the appliance's `Room.soundsConfig` field."""

    def __init__(self, device: MilaAppliance):
        super().__init__(device, "Sound Mode", "mdi:volume-high")
        # Last unrecognised soundsConfig value we warned about. HA reads
        # `current_option` on every coordinator refresh, so warning
        # unconditionally would repeat the same line every poll; this
        # limits it to once per distinct unknown value.
        self._warned_unknown_value: Optional[str] = None

    @property
    def unique_id(self) -> str:
        """Stable id is appliance-scoped (one select per appliance)."""
        return f"{DOMAIN}_{self.device.id}_soundmode".lower()

    @property
    def device(self) -> MilaAppliance:
        """Typed accessor."""
        return self._device  # type: ignore[return-value]

    @property
    def current_option(self) -> Optional[str]:
        """Humanised label for the current `Room.soundsConfig` value.

        The API returns the raw enum string ("DaytimeOnly"). HA's
        `SelectEntity` nulls out any current option that isn't present
        in `options`, and `options` holds the humanised labels, so the
        raw value must be translated here. Without the translation,
        "Enabled" and "Disabled" happened to match (single words look
        the same either way) but "DaytimeOnly" rendered as a permanent
        "unknown".
        """
        raw = self.device.get_value("room.soundsConfig")
        if raw is None:
            return None
        try:
            return MODE_MAPPING[SoundsConfig(raw)]
        except ValueError:
            # The server sent a value our enum doesn't know (a mode
            # added upstream). Surface "unknown" rather than crashing,
            # and log it once per distinct value so we learn about the
            # addition without flooding the log on every poll.
            if raw != self._warned_unknown_value:
                self._warned_unknown_value = raw
                _LOGGER.warning("Unknown Mila sounds config value: %r", raw)
            return None

    @property
    def options(self) -> list[str]:
        """User-visible options (humanised labels)."""
        return list(MODE_MAPPING.values())

    async def async_select_option(self, option: str) -> None:
        """Send the chosen option to the API as a `SoundsConfig` enum."""
        if option not in self.options:
            _LOGGER.warning("'%s' is not a valid select option", option)
            return
        await self.device.set_sound_mode(INV_MODE_MAPPING[option])
