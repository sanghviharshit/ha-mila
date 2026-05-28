"""Device wrapper for a single Mila air purifier.

`MilaAppliance` is the bridge between cached coordinator data and the
collection of Home Assistant entities (fan, sensors, switches, select)
that represent one physical purifier. It also owns the write paths for
every user-driven change (fan speed, smart mode, sound mode, bedtime),
translating each into the right call on `MilaApi`.

Important detail about the live API: every write mutation targets a
*room*, not an appliance. We carry the room id alongside the appliance
id and use it whenever a write needs to happen.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from benedict import benedict
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..api import (
    ApplianceSensorKind,
    FanSpeed,
    MilaApi,
    PerformanceMode,
    PerformanceProfile,
    SmartModeKind,
    SoundsConfig,
)
from ..fan_speed import percentage_to_fan_speed_enum
from ..util import camel_case_split, coalesce
from .device import MilaDevice

_LOGGER = logging.getLogger(__name__)


def _to_utc(value: Any) -> Optional[datetime]:
    """Force a datetime to be timezone-aware (UTC).

    The API client's `_coerce_epoch_seconds` already returns UTC-aware
    datetimes, but a future API change or a different timestamp source
    might return naive ones. Home Assistant's `TIMESTAMP` device class
    rejects naive datetimes, so we attach UTC defensively. `None` and
    non-datetime values pass through unchanged.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return value


class MilaAppliance(MilaDevice):
    """A single Mila air purifier (and the entities it spawns)."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: MilaApi,
        device_id: str,
    ) -> None:
        """Inherit the base wiring; nothing appliance-specific to set up."""
        super().__init__(coordinator, api, device_id)

    # ----- Identity / availability ------------------------------------

    @property
    def name(self) -> str:
        """Build a friendly name with sensible fallbacks.

        Preferred order:
          1. The custom name the user set in the Mila app.
          2. The room's name ("Bedroom", "Office", ...).
          3. The room kind humanised: `LivingRoom` -> `Living Room`.
        """
        # `room.kind` is a PascalCase enum (`LivingRoom`, `KidsBedroom`,
        # ...). Splitting on camel-case boundaries makes it readable.
        room_kind = " ".join(camel_case_split(str(self._device_data["room.kind"])))
        return coalesce(
            self._device_data["name"] or None,
            self._device_data["room.name"] or None,
            room_kind,
        )

    @property
    def room_id(self) -> str:
        """ID of the room this appliance lives in.

        Every write mutation in the live API is room-scoped, so we
        cache this for convenience. Read-only on the appliance side.
        """
        return self._device_data["room.id"]

    @property
    def available(self) -> bool:
        """Whether HA should mark this device as available.

        The API returns `state.actualMode = null` when the appliance is
        offline. Treating that as unavailable greys out the entity in
        the UI rather than showing stale numbers.
        """
        return self._device_data["state.actualMode"] is not None

    @property
    def _device_data(self) -> benedict:
        """The slice of cached data that belongs to this appliance."""
        return self._appliance_data[self.id]

    # ----- Convenience accessors used by entities ---------------------

    def get_smart_modes(self) -> Optional[Dict[str, Any]]:
        """Return the `room.smartModes` payload (or None if not loaded).

        Used by `MilaSmartModeSwitch.is_on` to look up the current
        on/off state of each smart mode without going through the API.
        """
        return self._device_data.get("room.smartModes") or None

    def _current_performance_config(self) -> Dict[str, Any]:
        """Cached `room.performanceConfig` (mode/profile/fanSpeed).

        `applyRoomPerformanceConfig` requires every field every time,
        so the fan setter reads the current values from here and
        substitutes only the fields it wants to change.
        """
        return self._device_data.get("room.performanceConfig") or {}

    # ----- Write paths -------------------------------------------------
    #
    # Every method below does two things: send a mutation to Mila and
    # ask the coordinator to refresh. The refresh request is non-
    # blocking; HA will run it as soon as the current update cycle
    # finishes.

    async def set_smart_mode(self, mode: SmartModeKind, is_enabled: bool) -> None:
        """Toggle one smart mode (Quiet, Sleep, Whitenoise, ...) on or off."""
        await self._api.apply_smart_mode(self.room_id, mode, is_enabled)
        await self._coordinator.async_request_refresh()

    async def set_sound_mode(self, mode: SoundsConfig) -> None:
        """Change the appliance sounds setting (Enabled/DaytimeOnly/Disabled)."""
        await self._api.apply_sounds_config(self.room_id, mode)
        await self._coordinator.async_request_refresh()

    async def set_local_bedtime(self, local_start: str, local_end: str) -> None:
        """Backend for the `mila.set_bedtime` service. Takes HH:MM[:SS] strings."""
        await self._api.apply_local_bedtime(self.room_id, local_start, local_end)
        await self._coordinator.async_request_refresh()

    async def set_fan_mode(self, mode: str) -> None:
        """Switch between Automagic (auto) and Manual.

        Carries the current `profile` and `fanSpeed` forward so a mode
        change doesn't accidentally also reset the user's chosen speed.
        Falls back to sensible defaults (`Normal` + `Speed50`) on the
        first call if cached state is empty.
        """
        perf = self._current_performance_config()
        target_mode = (
            PerformanceMode.Automatic if mode == "Automagic" else PerformanceMode.Manual
        )
        await self._api.apply_performance_config(
            self.room_id,
            mode=target_mode,
            profile=perf.get("profile") or PerformanceProfile.Normal,
            fan_speed=perf.get("fanSpeed") or FanSpeed.Speed50,
        )
        await self._coordinator.async_request_refresh()

    async def set_fan_speed(self, percentage: Optional[int]) -> None:
        """Set a specific manual fan speed (0-100 %).

        Switches the room into `Manual` mode if it isn't already and
        sets `fanSpeed` to the matching enum value. After the mutation
        we call `force_room_data` so the next poll sees the new RPM
        immediately instead of waiting for the appliance's own push
        cycle.
        """
        perf = self._current_performance_config()
        await self._api.apply_performance_config(
            self.room_id,
            mode=PerformanceMode.Manual,
            profile=perf.get("profile") or PerformanceProfile.Normal,
            fan_speed=percentage_to_fan_speed_enum(percentage),
        )
        await self._api.force_room_data(self.room_id)
        await self._coordinator.async_request_refresh()

    # ----- Entity construction ----------------------------------------

    def _get_all_entities(self) -> List[Entity]:
        """Build the per-appliance entity list.

        Imports are deferred inside the method because the entities
        package imports back into this module (a `MilaAppliance` is
        passed to every entity's constructor). The lazy import keeps
        the import cycle from blowing up at module load.
        """
        from ..entities import (
            MilaApplianceFan,
            MilaApplianceMeasurementSensor,
            MilaAppliancePathSensor,
            MilaSmartModeSwitch,
            MilaSoundModeSelect,
            TVOC_PPB_TO_UGM3,
        )

        # The list below is intentionally explicit rather than data-driven:
        # each entity here represents a distinct user-visible knob in HA,
        # and adding/removing one is a deliberate decision rather than
        # an automatic side-effect of a config table.
        return [
            # Diagnostic-y path sensors: scalar values pulled straight
            # from the appliance payload by dotted path.
            MilaAppliancePathSensor(
                self,
                "Mode",
                "state.actualMode",
                icon="mdi:state-machine",
                # `actualMode` is a `_StrValueEnum`; cast to str so HA
                # writes the bare value into state rather than the
                # `EnumName.Member` form.
                convert_function=lambda v: str(v) if v is not None else None,
            ),
            MilaAppliancePathSensor(
                self,
                "Wifi Strength",
                "state.wifiRssi",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                uom=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                icon="mdi:wifi",
            ),
            MilaAppliancePathSensor(
                self,
                "Filter Kind",
                "filter.kind",
                icon="mdi:hvac",
                # Same enum-stringify treatment as `actualMode`.
                convert_function=lambda v: str(v) if v is not None else None,
            ),
            MilaAppliancePathSensor(
                self,
                "Filter Install Date",
                "filter.installedAt",
                device_class=SensorDeviceClass.TIMESTAMP,
                icon="mdi:calendar-refresh",
                convert_function=_to_utc,
            ),
            MilaAppliancePathSensor(
                self,
                "Filter Calibrated Date",
                "filter.calibratedAt",
                device_class=SensorDeviceClass.TIMESTAMP,
                icon="mdi:calendar",
                convert_function=_to_utc,
            ),
            MilaAppliancePathSensor(
                self,
                "Bedtime Start",
                "room.bedtime.localStart",
                icon="mdi:calendar-start",
            ),
            MilaAppliancePathSensor(
                self,
                "Bedtime End",
                "room.bedtime.localEnd",
                icon="mdi:calendar-end",
            ),

            # Sensors backed by the `sensors[]` array (one per measurement
            # kind requested in `GET_APPLIANCES`).
            MilaApplianceMeasurementSensor(
                self, "Air Changes", ApplianceSensorKind.Ach,
                uom="cph", icon="mdi:cloud-refresh", precision=1,
            ),
            MilaApplianceMeasurementSensor(
                self, "Air Quality", ApplianceSensorKind.Aqi,
                device_class=SensorDeviceClass.AQI,
            ),
            MilaApplianceMeasurementSensor(
                self, "CO", ApplianceSensorKind.Co,
                device_class=SensorDeviceClass.CO,
                uom=CONCENTRATION_PARTS_PER_MILLION,
            ),
            MilaApplianceMeasurementSensor(
                self, "CO2", ApplianceSensorKind.Co2,
                device_class=SensorDeviceClass.CO2,
                uom=CONCENTRATION_PARTS_PER_MILLION,
            ),
            MilaApplianceMeasurementSensor(
                self, "Fan Speed", ApplianceSensorKind.FanSpeed,
                uom="rpm", icon="mdi:fan", precision=1,
            ),
            MilaApplianceMeasurementSensor(
                self, "Humidity", ApplianceSensorKind.Humidity,
                device_class=SensorDeviceClass.HUMIDITY,
                uom=PERCENTAGE, precision=1,
            ),
            MilaApplianceMeasurementSensor(
                self, "PM1", ApplianceSensorKind.Pm1,
                device_class=SensorDeviceClass.PM1,
                uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            ),
            MilaApplianceMeasurementSensor(
                self, "PM10", ApplianceSensorKind.Pm10,
                device_class=SensorDeviceClass.PM10,
                uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            ),
            MilaApplianceMeasurementSensor(
                self, "PM2.5", ApplianceSensorKind.Pm2_5,
                device_class=SensorDeviceClass.PM25,
                uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            ),
            MilaApplianceMeasurementSensor(
                self, "Time To Clean", ApplianceSensorKind.Ttc,
                device_class=SensorDeviceClass.DURATION,
                uom="min", icon="mdi:timer-sand",
            ),
            MilaApplianceMeasurementSensor(
                self, "VOC", ApplianceSensorKind.Voc,
                device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
                uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
                # Mila reports VOC as ppb; we present it as ug/m^3 to
                # match HA's standard unit. The factor is empirical
                # (see `entities/appliance/const.py`).
                uom_conversion_factor=TVOC_PPB_TO_UGM3,
            ),
            MilaApplianceMeasurementSensor(
                self, "Temperature", ApplianceSensorKind.Temperature,
                uom=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                precision=1,
            ),

            # Smart-mode toggles. PowerSaver is intentionally absent;
            # the live API doesn't expose a toggle for it (the appliance
            # enters PowerSaver automatically).
            MilaSmartModeSwitch(self, "Quiet", SmartModeKind.Quiet, "mdi:ear-hearing-off"),
            MilaSmartModeSwitch(self, "Quarantine", SmartModeKind.Quarantine, "mdi:virus"),
            MilaSmartModeSwitch(self, "Child Lock", SmartModeKind.ChildLock, "mdi:lock"),
            MilaSmartModeSwitch(self, "Housekeeper", SmartModeKind.Housekeeper, "mdi:broom"),
            MilaSmartModeSwitch(self, "Sleep", SmartModeKind.Sleep, "mdi:sleep"),
            MilaSmartModeSwitch(self, "Turndown", SmartModeKind.Turndown, "mdi:bed"),
            MilaSmartModeSwitch(self, "Whitenoise", SmartModeKind.Whitenoise, "mdi:waveform"),

            # The fan itself (speed control + preset modes) and the
            # sounds-mode select dropdown.
            MilaApplianceFan(self),
            MilaSoundModeSelect(self),
        ]

    def _get_software_version(self) -> str:
        """Firmware version for the device-info card."""
        return self._device_data["state.firmware.version"]
