"""The fan entity for a Mila air purifier.

This is the most state-heavy entity in the integration because Home
Assistant's `FanEntity` expects the entity to *be* the source of truth
for percentage, preset mode, and on/off, even though the underlying
state actually lives on the Mila API.

To keep the UI responsive when the user moves the speed slider:

1. The user changes the percentage in HA.
2. We send `applyRoomPerformanceConfig` (via the device wrapper) and
   stash the requested percentage as `_percentage_override` so the
   `percentage` property returns the user's target rather than the
   stale cached RPM.
3. We register a coordinator listener (`_update_listener`) that clears
   `_percentage_override` once a fresh poll lands a real reading
   within 10 % of the target.

Without the override, the UI snaps back to the previous percentage
during the second or two between sending the mutation and getting a
fresh poll cycle.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import time
from typing import List, Optional

from homeassistant.components.fan import FanEntityFeature

from ...api import ApplianceMode, ApplianceSensorKind
from ...const import DOMAIN
from ...devices import MilaAppliance
from ...fan_speed import FAN_SPEED_COUNT, rpm_to_percentage
from ..common import MilaFan
from .const import PRESET_MODE_AUTOMAGIC, PRESET_MODE_MANUAL, PRESET_MODES

_LOGGER = logging.getLogger(__name__)


class MilaApplianceFan(MilaFan):
    """Representation of the Mila Fan in Home Assistant."""

    def __init__(self, device: MilaAppliance):
        # `"Fan"` is the entity-local suffix; the base class composes
        # the full label as e.g. "Bedroom Fan".
        super().__init__(device, "Fan", "mdi:fan")

        # Preset modes are exposed verbatim from `const.py`; we only
        # have two (Automagic, Manual) but they're handled identically
        # to a larger preset list.
        self._preset_modes = PRESET_MODES

        # Bitmask of `FanEntityFeature` values we support. SET_SPEED
        # gives the percentage slider; PRESET_MODE gives the Automagic
        # vs Manual dropdown; TURN_ON / TURN_OFF give the on/off
        # buttons. Some HA UIs hide entities that don't declare
        # TURN_ON/OFF, so we always include them.
        self._supported_features = (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
        )

        # Number of discrete speed steps the slider should snap to.
        # `FAN_SPEED_COUNT` is 10 (matching Mila's 10 %-step model).
        self._speed_count = FAN_SPEED_COUNT

        # Optimistic local state to bridge the gap between sending a
        # speed change and receiving a fresh reading. See module
        # docstring for the lifecycle.
        self._percentage_override: Optional[float] = None

        # Subscribe to coordinator updates so we can clear the
        # optimistic override once the real reading catches up.
        self.device.add_update_listener(self._update_listener)

    @property
    def unique_id(self) -> str:
        """Stable id — one fan per appliance."""
        return f"{DOMAIN}_{self.device.id}_fan".lower()

    @property
    def device(self) -> MilaAppliance:
        """Typed accessor."""
        return self._device  # type: ignore[return-value]

    @property
    def speed(self) -> Optional[float]:
        """Current RPM as reported by the FanSpeed sensor.

        Used internally to derive the `percentage` and `is_on`
        properties. Returns None if no reading is cached yet.
        """
        sensors: List = self.device.get_value("sensors")
        sensor = next(
            (s for s in sensors if s["kind"] == ApplianceSensorKind.FanSpeed),
            None,
        )
        return sensor["latest"]["value"] if sensor else None

    @property
    def current_mode(self) -> Optional[ApplianceMode]:
        """The appliance's active `ApplianceMode` (read-only state)."""
        return self.device.get_value("state.actualMode")

    @property
    def is_on(self) -> bool:
        """True if the fan is spinning (any RPM above 0)."""
        return self.speed is not None and self.speed > 0

    @property
    def supported_features(self):
        """Required by HA's FanEntity to discover which methods to call."""
        return self._supported_features

    @property
    def preset_modes(self) -> list:
        """List of selectable preset modes for the UI dropdown."""
        return self._preset_modes

    @property
    def percentage(self):
        """User-facing fan speed as 0-100 %.

        Prefers the optimistic override if one is set (so the UI
        doesn't lag behind a slider drag). Otherwise maps the live
        RPM sensor onto Mila's stepped percentage table.
        """
        if self.speed is None:
            return None
        if self._percentage_override is not None:
            return self._percentage_override
        return rpm_to_percentage(self.speed)

    @property
    def speed_count(self):
        """Number of discrete steps the UI should snap the slider to."""
        return self._speed_count

    @property
    def preset_mode(self) -> str:
        """Current preset mode label.

        We collapse every non-Manual ApplianceMode (Automagic, Sleep,
        Quiet, PowerSaver, ...) into "Automagic" because the preset
        selector only has two slots. The specific underlying mode is
        still visible via `extra_state_attributes["actual_mode"]`.
        """
        return (
            PRESET_MODE_MANUAL
            if self.current_mode == ApplianceMode.Manual
            else PRESET_MODE_AUTOMAGIC
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Surface secondary state on the entity as attributes.

        These don't drive any HA UI directly but are useful for
        automations and templating (e.g. "if actual_mode is
        'PowerSaver' then ..."). Returning only the keys with values
        keeps the attribute payload tidy.
        """
        attrs: dict = {}

        actual = self.device.get_value("state.actualMode")
        if actual is not None:
            attrs["actual_mode"] = str(actual)

        # `state.modes` is the full list of modes currently applied
        # (often `[actualMode]` but sometimes a superset).
        modes = self.device.get_value("state.modes")
        if modes:
            attrs["active_modes"] = [str(m) for m in modes]

        # Bedtime window — the same data is also available as standalone
        # sensors, but having it on the fan attributes makes it easy to
        # use in automations gated on whether the fan should run at
        # night-time speeds.
        bedtime_start = self.device.get_value("room.bedtime.localStart")
        bedtime_end = self.device.get_value("room.bedtime.localEnd")
        if bedtime_start is not None:
            attrs["bedtime_start"] = str(bedtime_start)
        if bedtime_end is not None:
            attrs["bedtime_end"] = str(bedtime_end)

        # Sound mode (also a dedicated select entity).
        sounds = self.device.get_value("room.soundsConfig")
        if sounds is not None:
            attrs["sounds_config"] = str(sounds)

        # Smart modes as a flat dict of {name: isEnabled}. Useful for
        # building lovelace cards that show all toggles in one place.
        smart_modes = self.device.get_smart_modes()
        if smart_modes:
            attrs["smart_modes"] = {
                name: bool(state.get("isEnabled"))
                for name, state in smart_modes.items()
                if isinstance(state, dict) and "isEnabled" in state
            }

        return attrs

    # ----- Turn-on / turn-off / set-speed / set-preset ---------------

    async def async_turn_on(
        self,
        speed: str = None,           # legacy HA pre-2022 arg
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """HA-driven on. Behaviour depends on which optional args were given.

        * percentage supplied  -> manual mode at that percentage.
        * preset_mode supplied -> apply the preset.
        * neither supplied     -> default to Automagic (the smart mode).
        """
        if percentage:
            await self.async_set_percentage(percentage)
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        if percentage is None and preset_mode is None:
            # "Just turn on" -> let the appliance choose a speed.
            await self.async_set_preset_mode(PRESET_MODE_AUTOMAGIC)

    async def async_turn_off(self, **kwargs) -> None:
        """HA-driven off. Equivalent to setting the fan to 0 %."""
        # We send 0 through the same code path so the optimistic
        # override + manual-mode promotion logic runs identically.
        await self.async_set_percentage(0)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed in percent. Promotes to Manual if currently Automagic."""
        # Setting a specific percentage only makes sense in Manual mode,
        # so switch first. The API allows manual + a specific
        # `fanSpeed` enum value to be applied in one call, but we go
        # through the preset-mode change so the entity state stays
        # consistent with what HA shows.
        if self.preset_mode == PRESET_MODE_AUTOMAGIC:
            await self.async_set_preset_mode(PRESET_MODE_MANUAL)
        await self.device.set_fan_speed(percentage)
        # Briefly wait so the mutation has time to land before the
        # next refresh fires; the override below covers the rest of
        # the gap.
        await asyncio.sleep(1)
        self._percentage_override = percentage

    async def async_set_bedtime(
        self, local_start: time, local_end: time
    ) -> None:
        """Service handler for `mila.set_bedtime`.

        `local_start` and `local_end` come in as `datetime.time` from
        the service schema's `cv.time` validator. `isoformat()` gives
        the `HH:MM:SS` string the API's `LocalTime` scalar expects.
        """
        await self.device.set_local_bedtime(
            local_start.isoformat(), local_end.isoformat()
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between Automagic and Manual preset modes."""
        if preset_mode not in self.preset_modes:
            _LOGGER.warning("'%s' is not a valid preset mode", preset_mode)
            return

        _LOGGER.info("Setting the fan preset to %s", preset_mode)
        await self.device.set_fan_mode(preset_mode)

        # Going back to Automagic means the user no longer cares about
        # the last manual percentage, so clear the optimistic override.
        if preset_mode == PRESET_MODE_AUTOMAGIC:
            self._percentage_override = None

    def _update_listener(self) -> None:
        """Clear the optimistic override once the live reading catches up.

        Called by the coordinator on every refresh. We compare the
        cached RPM-derived percentage against the user's last target;
        if they're within one bucket (10 %), the device has caught up
        and we let HA fall back to the real reading.
        """
        if self._percentage_override is None:
            return
        live_pct = self.percentage
        if live_pct is None:
            return
        if abs(live_pct - self._percentage_override) < 10:
            self._percentage_override = None
