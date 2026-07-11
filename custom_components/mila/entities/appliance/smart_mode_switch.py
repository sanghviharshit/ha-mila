"""HA switch that toggles one smart mode (Quiet, Sleep, Whitenoise, ...).

State is read from `Room.smartModes.<name>.isEnabled` (lower-camelCase
field names on the GraphQL side; the local `SmartModeKind` enum uses
PascalCase). The MODE_MAPPING table at module scope precomputes the
translation so we don't do it in every `is_on` call.

Toggling fires `applyRoom<Name>Mode(roomId, isEnabled)` via the API
facade, which then asks the coordinator for a refresh so HA reflects
the new state without waiting a full poll cycle.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ...api import SmartModeKind
from ...const import DOMAIN
from ...devices import MilaAppliance
from ..common import MilaSwitch

_LOGGER = logging.getLogger(__name__)


# SmartModeKind members are PascalCase ("Quiet", "ChildLock", ...), but
# the Room.smartModes GraphQL object uses camelCase fields ("quiet",
# "childLock", ...). This map keeps the translation explicit and
# centralised; if Mila renames a field, only one line changes here.
MODE_MAPPING: dict[SmartModeKind, str] = {
    m: m.value[0].lower() + m.value[1:] for m in SmartModeKind
}


class MilaSmartModeSwitch(MilaSwitch):
    """One smart-mode toggle, with on/off state pulled from cached data."""

    def __init__(
        self,
        device: MilaAppliance,
        name: str,
        smartmode_kind: SmartModeKind,
        icon: Optional[str] = None,
    ):
        super().__init__(device, name, icon)
        self._smartmode_kind = smartmode_kind

    @property
    def unique_id(self) -> str:
        """Stable id is appliance id + smart-mode kind."""
        return (
            f"{DOMAIN}_{self.device.id}_smartmode_{self._smartmode_kind}".lower()
        )

    @property
    def device(self) -> MilaAppliance:
        """Typed accessor."""
        return self._device  # type: ignore[return-value]

    @property
    def is_on(self) -> Optional[bool]:
        """Current on/off state from `Room.smartModes.<name>.isEnabled`.

        Returns None (HA renders this as "unknown") if smart-mode data
        isn't in the cache yet — typically only during the brief
        window between first refresh and entity registration.
        """
        smart_modes = self.device.get_smart_modes()
        if not smart_modes:
            return None
        # Map enum -> camelCase field name, then read `isEnabled`.
        node = smart_modes.get(MODE_MAPPING[self._smartmode_kind])
        if not isinstance(node, dict):
            return None
        return node.get("isEnabled")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Persist the on state via `applyRoom<Name>Mode`."""
        await self.device.set_smart_mode(self._smartmode_kind, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Persist the off state via `applyRoom<Name>Mode`."""
        await self.device.set_smart_mode(self._smartmode_kind, False)
