"""Support for MilaAir Purifier."""
import asyncio
import logging
from typing import Optional, List

from homeassistant.components.fan import (
    FanEntityFeature
)

from homeassistant.util.percentage import (
    ranged_value_to_percentage,
)

from milasdk import ApplianceSensorKind, ApplianceMode

_LOGGER = logging.getLogger(__name__)

from ...const import DOMAIN
from ...devices import MilaAppliance
from ..common import MilaFan
from .const import (
    MIN_FAN_RPM, 
    MAX_FAN_RPM, 
    PRESET_MODE_AUTOMAGIC, 
    PRESET_MODE_MANUAL, 
    PRESET_MODES,
    ROOM_GOAL_NORMAL_HUMAN,
    ROOM_GOAL_TO_PROFILE,
    PROFILE_TO_ROOM_GOAL,
    ROOM_GOAL_DETAILS,
)

class MilaApplianceFan(MilaFan):
    """Representation of the Mila Fan"""
    def __init__(
        self, 
        device: MilaAppliance
    ):
        super().__init__(device, "Fan", "mdi:fan")      
        self._preset_modes = PRESET_MODES
        self._supported_features = (
            FanEntityFeature.SET_SPEED | 
            FanEntityFeature.PRESET_MODE |
            FanEntityFeature.TURN_ON |
            FanEntityFeature.TURN_OFF
        )
        self._speed_count = 10
        self._percentage_override: Optional[float] = None
        self._preset_mode_override: Optional[str] = None

        self.device.add_update_listener(self._update_listener)

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_fan".lower()

    @property
    def device(self) -> MilaAppliance:
        return self._device

    @property
    def speed(self) -> Optional[float]:
        sensors: List = self.device.get_value("sensors")
        sensor = next((i for i in sensors if i["kind"] == ApplianceSensorKind.FanSpeed), None)
        if sensor and "latest" in sensor and sensor["latest"] and "value" in sensor["latest"]:
            return sensor["latest"]["value"]
        return None

    @property
    def current_mode(self) -> ApplianceMode:
        return self.device.get_value("state.actualMode")

    @property
    def current_room_goal(self) -> Optional[str]:
        profile = self.device.get_value("room.performanceConfig.profile")
        return PROFILE_TO_ROOM_GOAL.get(profile)

    @property
    def is_on(self) -> bool:
        """Return true if the entity is on."""
        if self._percentage_override is not None:
            return self._percentage_override > 0
        if self._preset_mode_override is not None:
            if self._preset_mode_override in ROOM_GOAL_TO_PROFILE:
                return True
            return self.speed is not None and self.speed > 0
        if self.current_mode is not None and self.current_mode != ApplianceMode.Manual:
            return True
        return self.speed is not None and self.speed > 0

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    @property
    def preset_modes(self) -> list:
        """Get the list of available preset modes."""
        return self._preset_modes

    @property
    def percentage(self) -> Optional[int]:
        """Return the percentage based speed of the fan."""
        if self._percentage_override is not None:
            return int(self._percentage_override)
        if self.speed is None:
            return None
        if not self.is_on or self.speed <= 0:
            return 0
        raw_percentage = ranged_value_to_percentage(
            [MIN_FAN_RPM, MAX_FAN_RPM],
            max(MIN_FAN_RPM, min(MAX_FAN_RPM, self.speed))
        )
        pct = round(raw_percentage, -1)
        return int(max(10, min(100, pct)))

    @property
    def speed_count(self):
        """Return the number of speeds of the fan supported."""
        return self._speed_count

    @property
    def preset_mode(self) -> Optional[str]:
        """Get the active preset mode."""
        if self._preset_mode_override is not None:
            return self._preset_mode_override
        if self.current_mode == ApplianceMode.Manual:
            return PRESET_MODE_MANUAL
        return self.current_room_goal or ROOM_GOAL_NORMAL_HUMAN

    @property
    def extra_state_attributes(self) -> dict:
        """Return optional state attributes."""
        attrs = {}
        if self.speed is not None:
            attrs["current_rpm"] = self.speed
        if self.current_mode is not None:
            attrs["actual_mode"] = str(self.current_mode)
        if self.current_room_goal is not None:
            attrs["room_goal"] = self.current_room_goal
            goal_info = ROOM_GOAL_DETAILS.get(self.current_room_goal)
            if goal_info:
                attrs["air_changes_per_day"] = goal_info["air_changes_per_day"]
        return attrs

    async def async_turn_on(
        self,
        speed: str = None,
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """Turn the device on."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
        elif preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        else:
            target_preset = self.current_room_goal or ROOM_GOAL_NORMAL_HUMAN
            await self.async_set_preset_mode(target_preset)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        self._preset_mode_override = PRESET_MODE_MANUAL
        self._percentage_override = 0
        self.async_write_ha_state()
        await self.device.set_fan_speed(None)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the percentage of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return
        self._preset_mode_override = PRESET_MODE_MANUAL
        self._percentage_override = percentage
        self.async_write_ha_state()
        await self.device.set_fan_speed(percentage)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode == PRESET_MODE_AUTOMAGIC:
            preset_mode = self.current_room_goal or ROOM_GOAL_NORMAL_HUMAN

        if preset_mode not in self.preset_modes:
            _LOGGER.warning("'%s' is not a valid preset mode", preset_mode)
            return

        _LOGGER.info(f"Setting the fan preset mode to {preset_mode}")
        self._preset_mode_override = preset_mode

        if preset_mode == PRESET_MODE_MANUAL:
            self.async_write_ha_state()
            await self.device.set_fan_mode(PRESET_MODE_MANUAL, speed=self.percentage)
        elif preset_mode in ROOM_GOAL_TO_PROFILE:
            self._percentage_override = None
            self.async_write_ha_state()
            profile = ROOM_GOAL_TO_PROFILE[preset_mode]
            await self.device.set_room_goal(profile)

    def _update_listener(self) -> None:
        if self._preset_mode_override is not None:
            if self._preset_mode_override == PRESET_MODE_MANUAL:
                if self.current_mode == ApplianceMode.Manual:
                    self._preset_mode_override = None
            else:
                if self.current_mode != ApplianceMode.Manual and self.current_room_goal == self._preset_mode_override:
                    self._preset_mode_override = None

        if self._percentage_override is not None:
            if self._percentage_override == 0:
                if self.speed is not None and self.speed <= 0:
                    self._percentage_override = None
                    self.async_write_ha_state()
            elif self.percentage is not None and abs(self.percentage - self._percentage_override) < 10:
                self._percentage_override = None
                self.async_write_ha_state()
