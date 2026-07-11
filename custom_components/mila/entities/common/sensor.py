"""Base class for every Mila sensor entity.

`SensorEntity` carries a bunch of useful `_attr_*` slots: native value,
unit of measurement, device class, state class. We accept them all in
the constructor so subclasses don't have to repeat the boilerplate, and
HA's `SensorEntity` reads them automatically.

Concrete subclasses provide `unique_id` and `native_value`. Most
appliance and location sensors are thin path-walkers over cached
coordinator data; the only logic-heavy subclass is the AQI sensor
(which converts PM2.5 to AQI via `python-aqi`).
"""
from __future__ import annotations

from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from ...devices import MilaDevice
from .entity import MilaEntity


class MilaSensor(MilaEntity, SensorEntity):
    """`MilaEntity` + `SensorEntity` with the usual sensor attributes prewired."""

    def __init__(
        self,
        device: MilaDevice,
        name: str,
        icon: Optional[str] = None,
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
    ):
        super().__init__(device)
        self._name = name
        # `_attr_*` slots are what HA reads to build the entity state
        # payload. Setting them in the constructor means each subclass
        # only has to override the *value* property (`native_value`).
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = uom
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def unique_id(self) -> str:
        """Subclass-defined stable id."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """Compose device name + entity-local suffix."""
        return f"{self.device.name_or_id} {self._name}"

    @property
    def native_value(self):
        """The displayed sensor reading. Subclasses must override."""
        raise NotImplementedError
