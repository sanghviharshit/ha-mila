"""The fan entity for a Mila air purifier.

This is the most state-heavy entity in the integration because Home
Assistant's `FanEntity` expects the entity to *be* the source of truth
for percentage, preset mode, and on/off, even though the underlying
state actually lives on the Mila API.

To keep the UI responsive when the user moves the speed slider:

1. The user changes the percentage in HA.
2. We stash the requested percentage as `_percentage_override` (and
   push a state write) BEFORE sending `applyRoomPerformanceConfig`, so
   the `percentage` property returns the user's target rather than the
   stale cached RPM for the whole round trip. If the mutation fails,
   the override is rolled back so the UI doesn't show a change that
   never happened.
3. A coordinator listener (`_update_listener`) clears
   `_percentage_override` once a fresh poll lands a real RPM-derived
   reading within 10 % of the target. The comparison must use the raw
   RPM mapping, not the `percentage` property: that property returns
   the override itself while one is set, so comparing it against the
   override would always match and clear the override on the very
   first refresh, stale or not.

Without the override, the UI snaps back to the previous percentage
during the gap between sending the mutation and the first poll that
reflects the new speed.
"""
from __future__ import annotations

import logging
from datetime import time
from typing import Optional

from homeassistant.components.fan import FanEntityFeature

from ...api import ApplianceMode, ApplianceSensorKind
from ...const import DOMAIN
from ...devices import MilaAppliance
from ...fan_speed import FAN_SPEED_COUNT, rpm_to_percentage
from ..common import MilaFan
from .const import PRESET_MODE_AUTOMAGIC, PRESET_MODE_MANUAL, PRESET_MODES

_LOGGER = logging.getLogger(__name__)

# How many coordinator refreshes an optimistic percentage override may
# survive without the live RPM catching up before we discard it and
# fall back to the real reading. The override is cleared on the refresh
# *after* this many, so it lives at most four poll cycles: roughly
# eight minutes at the default 120 s scan interval.
_OVERRIDE_MAX_REFRESHES = 3


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
        # Refreshes seen since the override was set. Safety valve: if
        # the device never converges on the target (Automagic took back
        # control, appliance clamped the speed), the override would
        # otherwise show the user's target forever. After
        # `_OVERRIDE_MAX_REFRESHES` polls we surrender to the live
        # reading whether or not it caught up.
        self._override_refresh_count = 0

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
        properties. Returns None if no reading is cached yet. Every
        step is guarded because the payload can legitimately thin out:
        `sensors` is None for an offline appliance, and `latest` is
        null when no sample landed inside the query's precision window.
        """
        sensors = self.device.get_value("sensors") or []
        sensor = next(
            (s for s in sensors if s.get("kind") == ApplianceSensorKind.FanSpeed),
            None,
        )
        if sensor is None:
            return None
        latest = sensor.get("latest") or {}
        return latest.get("value")

    @property
    def current_mode(self) -> Optional[ApplianceMode]:
        """The appliance's active `ApplianceMode` (read-only state)."""
        return self.device.get_value("state.actualMode")

    @property
    def is_on(self) -> bool:
        """True if the fan is spinning (any RPM above 0).

        Honours the optimistic override so a just-issued turn-off shows
        as "off" immediately instead of staying "on" until the RPM
        reading catches up (and vice versa for turn-on).
        """
        if self._percentage_override is not None:
            return self._percentage_override > 0
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
        doesn't lag behind a slider drag), even when no RPM reading is
        cached yet. Otherwise maps the live RPM sensor onto Mila's
        stepped percentage table.
        """
        if self._percentage_override is not None:
            return self._percentage_override
        if self.speed is None:
            return None
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
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """HA-driven on. Behaviour depends on which optional args were given.

        * percentage supplied  -> manual mode at that percentage (wins
                                  over preset_mode if both arrive,
                                  since a specific speed implies
                                  Manual; applying the preset first
                                  would fire an extra mutation carrying
                                  the stale cached speed).
        * preset_mode supplied -> apply the preset.
        * neither supplied     -> default to Automagic (the smart mode).

        Checks are `is not None`, not truthiness: a percentage of 0 is
        a valid (if unusual) request meaning "off", and a truthy check
        would silently do nothing with it.

        Signature note: HA core's fan service handler invokes this
        POSITIONALLY as `async_turn_on(percentage, preset_mode)`, so
        the parameter order here must match core's exactly. This is
        also why the legacy pre-2022 leading `speed` parameter had to
        go: with it in first position, core's positional call bound
        the percentage into `speed` (ignored) and the preset string
        into `percentage`.
        """
        if percentage is not None:
            await self.async_set_percentage(percentage)
        elif preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        else:
            # "Just turn on" -> let the appliance choose a speed.
            await self.async_set_preset_mode(PRESET_MODE_AUTOMAGIC)

    async def async_turn_off(self, **kwargs) -> None:
        """HA-driven off. Equivalent to setting the fan to 0 %."""
        # We send 0 through the same code path so the optimistic
        # override + manual-mode promotion logic runs identically.
        await self.async_set_percentage(0)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed in percent (0 turns the fan off).

        `MilaAppliance.set_fan_speed` sends `mode=Manual` and the
        target speed in a single `applyRoomPerformanceConfig` call, so
        there is no separate preset-mode mutation here. (There used to
        be one, and because it carried the stale cached `fanSpeed`, a
        turn-off from Automagic would briefly command the old speed
        before the real request landed.)

        The optimistic override is set BEFORE the API call so the UI
        reflects the user's target immediately; `_update_listener`
        clears it once a real reading catches up. On failure the
        override is rolled back so the UI doesn't keep showing a speed
        the appliance never accepted.
        """
        previous_override = self._percentage_override
        self._percentage_override = percentage
        self._override_refresh_count = 0
        self.async_write_ha_state()
        try:
            await self.device.set_fan_speed(percentage)
        except Exception:
            # Roll back only if the override is still ours: a second
            # set_percentage may have raced past this one while the
            # API call was in flight, and its newer target must not be
            # clobbered by our failure cleanup.
            if self._percentage_override == percentage:
                self._percentage_override = previous_override
                self.async_write_ha_state()
            raise

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
        RPM-derived percentage against the user's last target; if
        they're within one bucket (10 %), the device has caught up and
        we let HA fall back to the real reading.

        The comparison deliberately maps `self.speed` through
        `rpm_to_percentage` instead of reading `self.percentage`: that
        property returns the override itself while one is set, so
        comparing it against the override would always succeed and
        clear the override on the very first refresh even when the
        cached RPM is still the old speed.
        """
        if self._percentage_override is None:
            return
        # Safety valve: give up on the override after a few polls even
        # if the reading never converged (Automagic reclaimed control,
        # or the appliance clamped the requested speed). Counted before
        # the convergence check so a missing RPM reading also ages the
        # override out instead of latching it forever.
        self._override_refresh_count += 1
        if self._override_refresh_count > _OVERRIDE_MAX_REFRESHES:
            self._percentage_override = None
            return
        rpm = self.speed
        if rpm is None:
            return
        if abs(rpm_to_percentage(rpm) - self._percentage_override) < 10:
            self._percentage_override = None
