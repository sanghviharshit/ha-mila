"""Mila GraphQL enums, mirrored in Python.

Kept in-tree so the integration doesn't depend on any third-party SDK.
Each enum here corresponds to a `type X enum` in the live GraphQL schema
at `graph-api.milacares.com/graphql`. Member names and values match the
server exactly. If Mila adds or renames enum members on the server, this
file is the one place to update.

The base class is `_StrValueEnum`: a `str` subclass whose `.value` is the
member name. Subclassing `str` means an enum member can be passed
directly anywhere a string is expected (GraphQL variable values, JSON
payloads, logging). That avoids constantly calling `.value` at call
sites.
"""
from __future__ import annotations

from enum import Enum


class _StrValueEnum(str, Enum):
    """Enum base where `.value` equals the member name string.

    Subclassing `str` makes members work transparently in string contexts:

        SmartModeKind.Quiet == "Quiet"        # True
        json.dumps(SmartModeKind.Quiet)       # '"Quiet"'
        f"{SmartModeKind.Quiet}"              # "Quiet"

    Standard `Enum.__str__` returns "SmartModeKind.Quiet", which is no
    good for GraphQL variables. We override `__str__` to return the bare
    value instead.
    """

    def __str__(self) -> str:
        # Avoid the default "ClassName.MemberName" representation: when an
        # enum member is interpolated into a GraphQL request we want just
        # the member name (which equals the value).
        return self.value


# ---------------------------------------------------------------------------
# Appliance state enums (read-only on the wire).
# ---------------------------------------------------------------------------


class ApplianceMode(_StrValueEnum):
    """Read-only `ApplianceState.actualMode` field.

    Reports what the appliance is *doing right now*. Most members map to
    the matching `SmartModeKind` toggle the user enabled. A few are
    appliance-internal states the user can't directly switch on:

    * `DeepClean` — runs after `applyRoomDeepClean` (not currently used
      by the integration).
    * `Safeguard` — triggered when filter or hardware safety conditions
      need attention; shown to the user but not commanded.
    * `PowerSaver` — entered automatically when the room is unoccupied
      and energy efficiency profile is active. The user cannot toggle
      `PowerSaver` directly anymore (it used to be a `SmartModeKind`).
    """

    Automagic = "Automagic"
    Sleep = "Sleep"
    Housekeeper = "Housekeeper"
    DeepClean = "DeepClean"
    Quiet = "Quiet"
    Turndown = "Turndown"
    WhiteNoise = "WhiteNoise"
    Quarantine = "Quarantine"
    Manual = "Manual"
    Safeguard = "Safeguard"
    PowerSaver = "PowerSaver"


class SmartModeKind(_StrValueEnum):
    """Toggleable smart modes exposed as switches in Home Assistant.

    These correspond to fields on the `Room.smartModes` GraphQL object
    (using lower-camelCase: `quiet`, `childLock`, ...) and to the
    `applyRoom{Name}Mode` mutations.

    Note: `PowerSaver` from the older SDK is intentionally absent: the
    live API no longer exposes a mutation for it (the appliance enters
    PowerSaver state automatically rather than via a user toggle).
    """

    Housekeeper = "Housekeeper"
    Quiet = "Quiet"
    Quarantine = "Quarantine"
    Sleep = "Sleep"
    Turndown = "Turndown"
    Whitenoise = "Whitenoise"
    ChildLock = "ChildLock"


# ---------------------------------------------------------------------------
# Sensor identifiers.
# ---------------------------------------------------------------------------


class ApplianceSensorKind(_StrValueEnum):
    """Identifiers for the per-appliance sensor stream.

    Used both as a GraphQL argument (passing a list of kinds to
    `Appliance.sensors(kinds: [...])`) and as a dictionary key inside
    `MilaApplianceMeasurementSensor.native_value` to pick the right
    reading from the response.

    A few notable members:

    * `Ach` — Air Changes per Hour, a measure of how often the room's
      full volume of air has been filtered.
    * `Ttc` — Time To Clean, an estimate of minutes until the room
      reaches the appliance's target AQI.
    * `Pm2_5` — the underscore is on the server side; we keep the same
      spelling so this enum can be sent verbatim.
    """

    Ach = "Ach"
    FanSpeed = "FanSpeed"
    Ttc = "Ttc"
    Aqi = "Aqi"
    Pm1 = "Pm1"
    Pm2_5 = "Pm2_5"
    Pm10 = "Pm10"
    Voc = "Voc"
    Humidity = "Humidity"
    Temperature = "Temperature"
    Co2 = "Co2"
    Co = "Co"


# ---------------------------------------------------------------------------
# Fan / performance control enums.
# ---------------------------------------------------------------------------


class FanMode(_StrValueEnum):
    """Coarse fan speed used by Sleep/Turndown/Whitenoise mutations.

    Sleep mode runs the fan at `Lowest`, Turndown at `Highest`, and
    Whitenoise at `Medium`. The integration picks the matching value
    automatically when toggling these smart modes on.
    """

    Lowest = "Lowest"
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Highest = "Highest"


class FanSpeed(_StrValueEnum):
    """Stepped fan speed used by `applyRoomPerformanceConfig`.

    The live API exposes fan speed as a discrete enum rather than an RPM
    number: `TurnedOff` plus ten 10 % steps from `Speed10` to `Speed100`.
    This matches what the Mila mobile app shows on its speed slider.

    `fan_speed.percentage_to_fan_speed_enum` does the percentage->member
    translation when Home Assistant asks us to set a specific %.
    """

    TurnedOff = "TurnedOff"
    Speed10 = "Speed10"
    Speed20 = "Speed20"
    Speed30 = "Speed30"
    Speed40 = "Speed40"
    Speed50 = "Speed50"
    Speed60 = "Speed60"
    Speed70 = "Speed70"
    Speed80 = "Speed80"
    Speed90 = "Speed90"
    Speed100 = "Speed100"


class PerformanceMode(_StrValueEnum):
    """`Automatic` vs `Manual` on `Room.performanceConfig.mode`.

    `Automatic` is the user-friendly name for what the Mila app calls
    Automagic: the appliance decides fan speed based on measured AQI.
    `Manual` honours the explicit `FanSpeed` value.
    """

    Automatic = "Automatic"
    Manual = "Manual"


class PerformanceProfile(_StrValueEnum):
    """Strategy that biases the Automatic mode controller.

    `Normal` is the default; the others trade off filtration aggression
    versus noise and power use. We default to `Normal` when forming a
    `applyRoomPerformanceConfig` payload from scratch, but we carry the
    user's current value forward when changing only mode or speed.
    """

    MaxFiltration = "MaxFiltration"
    Moderate = "Moderate"
    Normal = "Normal"
    Quietest = "Quietest"
    EnergyEfficient = "EnergyEfficient"


class SoundsConfig(_StrValueEnum):
    """How the appliance announces alerts and confirmations.

    Drives the `select.sound_mode` entity. `DaytimeOnly` suppresses
    sounds during the room's configured bedtime window (see
    `mila.set_bedtime`).
    """

    Enabled = "Enabled"
    DaytimeOnly = "DaytimeOnly"
    Disabled = "Disabled"
