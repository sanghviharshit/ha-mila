"""Aggregate import surface for every Home Assistant entity class.

Three groups live underneath this package:

* `common/` — abstract base classes per HA platform (sensor, fan, ...)
  that hook each subclass into HA's coordinator pattern (auto-refresh
  on `async_added_to_hass`, expose `device_info`, etc.).
* `appliance/` — entities that belong to a Mila air purifier.
* `location/` — entities that belong to a household location (outdoor
  air station, pollen, AQI, distance).

The wildcard re-exports below keep callers (`devices/appliance.py`,
`devices/location.py`) tidy: they only need to import from
`..entities` rather than from each leaf module.
"""
from .appliance import *  # noqa: F401, F403
from .common import *  # noqa: F401, F403
from .location import *  # noqa: F401, F403
