import logging
from typing import Optional

from ...const import DOMAIN
from ...devices import MilaAppliance
from ..common import MilaSelect
from .const import (
    PROFILE_TO_ROOM_GOAL,
    ROOM_GOAL_DETAILS,
    ROOM_GOAL_TO_PROFILE,
)

_LOGGER = logging.getLogger(__name__)


class MilaRoomGoalSelect(MilaSelect):
    def __init__(self, device: MilaAppliance):
        super().__init__(device, "Room Goal", "mdi:target")
        self._current_option_override: Optional[str] = None
        self.device.add_update_listener(self._update_listener)

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_room_goal".lower()

    @property
    def device(self) -> MilaAppliance:
        return self._device

    @property
    def current_option(self) -> Optional[str]:
        if self._current_option_override is not None:
            return self._current_option_override
        try:
            profile = self.device.get_value("room.performanceConfig.profile")
            return PROFILE_TO_ROOM_GOAL.get(profile)
        except Exception as ex:
            _LOGGER.debug(f"Error getting room goal for {self.name}: {ex}")
            return None

    @property
    def options(self) -> list[str]:
        return list(ROOM_GOAL_TO_PROFILE.keys())

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        option = self.current_option
        if option and option in ROOM_GOAL_DETAILS:
            attrs["air_changes_per_day"] = ROOM_GOAL_DETAILS[option]["air_changes_per_day"]
            attrs["description"] = ROOM_GOAL_DETAILS[option]["description"]
        return attrs

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            _LOGGER.warning("'%s' is not a valid room goal option", option)
            return

        self._current_option_override = option
        self.async_write_ha_state()

        profile = ROOM_GOAL_TO_PROFILE[option]
        await self.device.set_room_goal(profile)

    def _update_listener(self) -> None:
        if self._current_option_override is not None:
            try:
                profile = self.device.get_value("room.performanceConfig.profile")
                if PROFILE_TO_ROOM_GOAL.get(profile) == self._current_option_override:
                    self._current_option_override = None
            except Exception:
                pass
