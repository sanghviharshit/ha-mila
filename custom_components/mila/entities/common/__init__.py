"""Shared base classes for every Mila entity.

Each module here defines one abstract base that mixes
`MilaEntity` (the coordinator-tied base) with an HA platform class
(`SensorEntity`, `SwitchEntity`, ...). Subclasses in
`entities/appliance/` and `entities/location/` only have to fill in the
`unique_id`, `native_value`, etc. that differ between entities.
"""
from .entity import MilaEntity
from .fan import MilaFan
from .select import MilaSelect
from .sensor import MilaSensor
from .switch import MilaSwitch

__all__ = ["MilaEntity", "MilaFan", "MilaSelect", "MilaSensor", "MilaSwitch"]
