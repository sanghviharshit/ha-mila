"""Small helpers used by location entities.

Currently only `to_pollen_index`: converts the API's textual pollen
severity into a numeric 0-4 scale that HA can graph / compare in
automations.
"""
from __future__ import annotations

import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)


# Order matches Mila's own colour-coded severity bands. "None" here is
# a sentinel string returned by the API (it has special handling on the
# server because GraphQL enums can't have a member named `None`).
POLLEN_INDEX_MAPPING = {
    "None": 0,
    "Low": 1,
    "Moderate": 2,
    "High": 3,
    "VeryHigh": 4,
}


def to_pollen_index(value: Optional[str]) -> Optional[int]:
    """Map a pollen severity label onto a 0-4 integer index.

    Returns `None` for missing values (so an absent pollen station
    silently shows up as `unknown` in HA rather than a crash) and for
    labels we don't recognise (logged at DEBUG so a server-side
    rename surfaces but doesn't spam the warning channel).
    """
    if value is None:
        return None
    try:
        return POLLEN_INDEX_MAPPING[value]
    except KeyError:
        _LOGGER.debug("Unknown pollen index value: %r", value)
        return None
