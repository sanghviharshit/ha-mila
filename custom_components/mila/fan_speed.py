"""Stepped percentage / RPM / FanSpeed-enum conversions for the fan entity.

The Mila air purifier expresses fan speed three different ways depending
on context:

* **Percentage (0-100, in 10 % steps)** — what Home Assistant's `FanEntity`
  exposes to users and what shows up in dashboards.
* **RPM (0, 600, 740, ...)** — what the `FanSpeed` sensor reports
  (literal rotational speed of the impeller).
* **FanSpeed enum (`TurnedOff`, `Speed10`...`Speed100`)** — what the live
  `applyRoomPerformanceConfig` mutation accepts.

The mapping between percentage and RPM is non-linear, mirroring the
table used by Mila's mobile app:

    | Percent | RPM  |
    |---------|------|
    |    0 %  |    0 |
    |   10 %  |  600 |
    |   20 %  |  740 |
    |   30 %  |  880 |
    |   40 %  | 1020 |
    |   50 %  | 1160 |
    |   60 %  | 1300 |
    |   70 %  | 1440 |
    |   80 %  | 1580 |
    |   90 %  | 1720 |
    |  100 %  | 2000 |

Reference: https://gist.github.com/sanghviharshit/913d14b225399e0fa4211b3e785671aa

Keeping the table central means every converter agrees on the rounding
behaviour: a value of 65 % rounds *down* to the 60 % step, matching what
the app does.
"""
from __future__ import annotations

from typing import Optional

# The full mapping as `(percentage, rpm)` tuples. Kept ordered so we can
# index into it directly by percentage // 10.
PERCENTAGE_RPM_STEPS: list[tuple[int, int]] = [
    (0, 0),
    (10, 600),
    (20, 740),
    (30, 880),
    (40, 1020),
    (50, 1160),
    (60, 1300),
    (70, 1440),
    (80, 1580),
    (90, 1720),
    (100, 2000),
]

# Home Assistant's `FanEntity` uses `speed_count` to decide how many
# discrete speed steps to draw on its slider UI. We have ten (the
# percentage entries from 10 % to 100 %; 0 % is "off", not a "speed").
FAN_SPEED_COUNT = 10


def percentage_to_rpm(percentage: Optional[int]) -> int:
    """Map a user-supplied percentage to the equivalent RPM value.

    Clamps to [0, 100] and rounds *down* to the nearest 10 % bucket
    before looking up the matching RPM. `None` is treated as 0 (off).

    Currently unused by the integration's control path (the live API
    takes a `FanSpeed` enum, not RPM), but kept here for symmetry and
    potential future use by callers that want to display "intended
    RPM" alongside the actual RPM sensor.
    """
    if percentage is None:
        return 0
    pct = max(0, min(100, int(percentage)))
    # Integer divide by 10 to land on the 10 %-step boundary, then index.
    idx = pct // 10
    return PERCENTAGE_RPM_STEPS[idx][1]


def rpm_to_percentage(rpm: Optional[float]) -> int:
    """Map a measured RPM reading back to the nearest percentage step.

    The fan never spins at the exact bucket RPM in practice (motor
    variation, target AQI overrides, etc.), so we pick the percentage
    bucket whose RPM is closest to the measurement.

    Returns 0 for `None` and for any non-positive RPM, so the fan
    entity correctly reports "off" when the device is stopped.
    """
    if rpm is None or rpm <= 0:
        return 0
    # `min(key=...)` picks the (pct, rpm) tuple with the smallest
    # absolute distance from the measured RPM. The first element of
    # the chosen tuple is the percentage.
    return min(PERCENTAGE_RPM_STEPS, key=lambda step: abs(step[1] - rpm))[0]


def percentage_to_fan_speed_enum(percentage: Optional[int]) -> str:
    """Map a percentage to a live `FanSpeed` enum value.

    The live `applyRoomPerformanceConfig` mutation takes the speed as
    one of `TurnedOff`, `Speed10`, `Speed20`, ..., `Speed100`. Anything
    that rounds down to 0 % becomes `TurnedOff`; everything else
    becomes `Speed{N}` where N is the rounded-down percentage.

    Returning a plain string (not an enum member) lets the API client
    accept either type uniformly via `str()`.
    """
    if percentage is None:
        return "TurnedOff"
    pct = max(0, min(100, int(percentage)))
    if pct == 0:
        return "TurnedOff"
    # Round down to a 10 % step (e.g. 65 -> 60).
    step = (pct // 10) * 10
    if step == 0:
        # A percentage in (0, 10) rounds down to 0; treat as off.
        return "TurnedOff"
    return f"Speed{step}"
