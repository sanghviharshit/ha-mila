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
    PRESET_MODES
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
    def is_on(self) -> bool:
        """Return true if the entity is on."""
        if self._percentage_override is not None:
            return self._percentage_override > 0
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
    def preset_mode(self):
        """Get the active preset mode."""
        return PRESET_MODE_MANUAL if self.current_mode == ApplianceMode.Manual else PRESET_MODE_AUTOMAGIC

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
            await self.async_set_preset_mode(PRESET_MODE_AUTOMAGIC)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        if self.preset_mode == PRESET_MODE_AUTOMAGIC:
            await self.async_set_preset_mode(PRESET_MODE_MANUAL)
        await self.device.set_fan_speed(None)
        self._percentage_override = 0
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the percentage of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return
        if self.preset_mode == PRESET_MODE_AUTOMAGIC:
            await self.async_set_preset_mode(PRESET_MODE_MANUAL)
        await self.device.set_fan_speed(percentage)
        self._percentage_override = percentage
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode not in self.preset_modes:
            _LOGGER.warning("'%s' is not a valid preset mode", preset_mode)
            return

        _LOGGER.info(f"Setting the fan mode to {preset_mode} speed")
        await self.device.set_fan_mode(preset_mode)
                
        if preset_mode == PRESET_MODE_AUTOMAGIC:
            self._percentage_override = None
        self.async_write_ha_state()

    def _update_listener(self) -> None:
        if self._percentage_override is None:
            return
        if self._percentage_override == 0:
            if self.speed is not None and self.speed <= 0:
                self._percentage_override = None
                self.async_write_ha_state()
        elif self.percentage is not None and abs(self.percentage - self._percentage_override) < 10:
            self._percentage_override = None
            self.async_write_ha_state()
