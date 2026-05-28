"""GraphQL strings the integration sends to the live Mila API.

Everything in this file is plain text. We deliberately don't import a
GraphQL client library (like `gql`) because:

1. The integration only sends a handful of fixed documents.
2. Schema validation lives on the server side; nothing local needs the
   1100-line schema definition.
3. Avoiding the dependency keeps the HACS install lightweight: HA already
   bundles `aiohttp`, so plain HTTP POST is the cheapest transport.

Each constant below was hand-verified against the live schema via
introspection (see `scripts/verify_new_client.py`). The mutations rely
on a few server quirks that aren't immediately obvious:

* `Duration` input takes a bare enum literal for `unit` (e.g. `Minute`)
  and an `Int!` for `value`. Quoting either is a validation error.
* `applyRoomPerformanceConfig` returns `ApplyRoomPerformanceConfigPayload`
  (which has only a `room` field). Every other write mutation returns
  `Room` directly.
* `smartModes` is a field on `Room`, not on `Appliance`. The older
  schema put it on `Appliance`; queries using that path now fail with
  `FieldUndefined`.
"""
from __future__ import annotations

from .enums import SmartModeKind

# The single GraphQL endpoint. Mila routes both reads and writes through
# this one URL using regular `Query` and `Mutation` operations.
GRAPHQL_URL = "https://graph-api.milacares.com/graphql"


# ---------------------------------------------------------------------------
# Read queries.
# ---------------------------------------------------------------------------


# Just the owner's profile (email, name). Used by the config-flow setup as
# a cheap sanity check that a token is valid, and by the coordinator on
# first refresh to populate `DATAKEY_ACCOUNT`.
GET_OWNER_PROFILE = """
query MilaGetOwnerProfile {
  owner { profile { email firstName lastName } }
}
"""


# Single round-trip query for every per-appliance piece of state the
# integration needs:
#
#   * `room.bedtime`           — nighttime window the user can edit
#   * `room.soundsConfig`      — for the select entity
#   * `room.smartModes`        — for the switch entities
#   * `room.performanceConfig` — current fan mode/profile/speed
#   * `state.*`                — firmware, RSSI, current ApplianceMode
#   * `filter.*`               — installed/calibrated timestamps
#   * `sensors(kinds: [...])`  — every measurement we expose as a sensor
#
# Doing this as one query (rather than one per appliance attribute)
# matters because most users have only one appliance, but the API
# rate-limits per request and a single large query is cheaper than many
# small ones.
GET_APPLIANCES = """
query MilaGetAppliances {
  owner {
    appliances {
      id
      name
      room {
        id
        kind
        name
        size
        soundsConfig
        bedtime { localStart localEnd }
        smartModes {
          quiet { isEnabled }
          housekeeper { isEnabled }
          quarantine { isEnabled }
          sleep { isEnabled fanMode }
          turndown { isEnabled fanMode }
          whitenoise { isEnabled fanMode }
          childLock { isEnabled }
        }
        performanceConfig { mode profile fanSpeed }
      }
      state {
        firmware { version hash }
        wifiRssi
        rawMode
        modes
        actualMode
      }
      filter { kind installedAt calibratedAt }
      sensors(kinds: [Ach, FanSpeed, Ttc, Aqi, Pm1, Pm2_5, Pm10, Voc, Humidity, Temperature, Co2, Co]) {
        kind
        latest(precision: { unit: Minute, value: 1 }) { instant value }
      }
    }
  }
}
"""


# Location data: outdoor station, pollen station, address. One per
# household. The pollen aggregateWindow exists but the SDK left it
# commented out historically (the schema response shape changes
# unpredictably). We omit it here for the same reason and let the
# coordinator fail soft if it ever wants to add it back later.
GET_LOCATIONS = """
query MilaGetLocations {
  owner {
    locations {
      id
      address {
        city
        country
        point { lat lon }
      }
      environmentKind
      homeKind
      houseSize
      houseAge
      houseBedrooms
      outdoorStation {
        id
        name
        point { lat lon }
        sensor(kind: Pm2_5) {
          kind
          latest(precision: { unit: Day, value: 1 }) { instant value }
        }
      }
      pollenStation { name }
      timezone
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Write mutations.
# ---------------------------------------------------------------------------


# Ask the appliance to push its latest sensor data immediately rather than
# waiting for its next periodic upload. We invoke this right after a
# manual fan-speed change so the next coordinator refresh sees the new
# RPM rather than the previous value.
FORCE_ROOM_DATA = """
mutation MilaForceRoomData($roomId: ID!) {
  forceRoomData(roomId: $roomId) { id }
}
"""


# Set the room's nighttime window. Triggered by the `mila.set_bedtime`
# service. Times are local to the room (the API stores them with no
# timezone; the appliance interprets them in the location's local TZ).
APPLY_ROOM_BEDTIME = """
mutation MilaApplyRoomBedtime($roomId: ID!, $localStart: LocalTime!, $localEnd: LocalTime!) {
  applyRoomBedtime(roomId: $roomId, localStart: $localStart, localEnd: $localEnd) {
    id
    bedtime { localStart localEnd }
  }
}
"""


# Set fan mode + speed in one shot. The schema requires the *entire*
# performance config in the input; you can't, for example, change only
# the mode while leaving profile/fanSpeed unspecified. `MilaApi.apply_
# performance_config` reads the current values from cached state before
# building this payload.
#
# Note the return shape: this is the only write mutation that returns a
# wrapper type (`ApplyRoomPerformanceConfigPayload`) with a `room`
# field, instead of returning `Room` directly. Selecting `id` at the top
# level would raise `FieldUndefined`.
APPLY_ROOM_PERFORMANCE_CONFIG = """
mutation MilaApplyRoomPerformanceConfig($input: ApplyRoomPerformanceConfigInput!) {
  applyRoomPerformanceConfig(input: $input) {
    room { id performanceConfig { mode profile fanSpeed } }
  }
}
"""


# Change Enabled / DaytimeOnly / Disabled for appliance sounds. Backs the
# `select.mila_sound_mode` entity.
APPLY_ROOM_SOUNDS_CONFIG = """
mutation MilaApplyRoomSoundsConfig($roomId: ID!, $soundsConfig: SoundsConfig!) {
  applyRoomSoundsConfig(roomId: $roomId, soundsConfig: $soundsConfig) {
    id
    soundsConfig
  }
}
"""


# Smart-mode mutations all share the same shape. The three that involve
# fan speed (Sleep, Turndown, Whitenoise) take an extra `fanMode`
# argument. Rather than literal-copy seven slightly different mutation
# strings, we build them once at import time via `smart_mode_mutation`.
_SMART_MODE_MUTATION_NAME = {
    SmartModeKind.Quiet: "applyRoomQuietMode",
    SmartModeKind.Housekeeper: "applyRoomHousekeeperMode",
    SmartModeKind.Quarantine: "applyRoomQuarantineMode",
    SmartModeKind.Sleep: "applyRoomSleepMode",
    SmartModeKind.Turndown: "applyRoomTurndownMode",
    SmartModeKind.Whitenoise: "applyRoomWhitenoiseMode",
    SmartModeKind.ChildLock: "applyRoomChildLockMode",
}

# The subset that requires a `fanMode` argument. The default (when
# applying) is `Medium` for whitenoise; Sleep/Turndown have their own
# server-side defaults (`Lowest` / `Highest`) which we honour by
# passing them explicitly.
SMART_MODES_WITH_FAN_MODE = {
    SmartModeKind.Sleep,
    SmartModeKind.Turndown,
    SmartModeKind.Whitenoise,
}


def smart_mode_mutation(kind: SmartModeKind) -> str:
    """Return the GraphQL mutation string for a single smart-mode toggle.

    The string is built once (per kind) at the first call site and is
    cheap enough to recompute, so we don't bother caching it. Operation
    name is `Mila<Mutation>` (e.g. `MilaApplyRoomQuietMode`) which makes
    server-side logs and traces easier to read.

    Args:
        kind: the `SmartModeKind` member being toggled.

    Returns:
        A valid GraphQL mutation document with `$roomId`, `$isEnabled`,
        and (for Sleep/Turndown/Whitenoise) `$fanMode` variables.
    """
    name = _SMART_MODE_MUTATION_NAME[kind]
    # The mutation field name starts lower-camel ("applyRoom..."), so we
    # upper-case the first letter to produce a TitleCase operation name.
    op = "Mila" + name[0].upper() + name[1:]
    params = ["$roomId: ID!", "$isEnabled: Boolean!"]
    args = ["roomId: $roomId", "isEnabled: $isEnabled"]
    if kind in SMART_MODES_WITH_FAN_MODE:
        params.append("$fanMode: FanMode!")
        args.append("fanMode: $fanMode")
    return (
        f"mutation {op}({', '.join(params)}) {{\n"
        f"  {name}({', '.join(args)}) {{ id }}\n"
        f"}}"
    )


def smart_mode_supported(kind: SmartModeKind) -> bool:
    """Whether the live API exposes a mutation for this smart mode.

    The `SmartModeKind` enum only contains kinds the server still
    accepts, so this is currently always `True`. Kept as an explicit
    check so future server-side removals can be reflected by deleting an
    entry from `_SMART_MODE_MUTATION_NAME` without breaking callers.
    """
    return kind in _SMART_MODE_MUTATION_NAME
