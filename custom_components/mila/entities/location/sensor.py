"""Shared base for every location-side sensor.

Mirrors the appliance side: this class only narrows the typed accessor
so subclasses can call location-specific helpers without a cast.
"""
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...devices import MilaLocation
from ..common import MilaSensor

_LOGGER = logging.getLogger(__name__)


class MilaLocationSensor(MilaSensor):
    """Base for every sensor on a `MilaLocation` device."""

    def __init__(
        self,
        device: MilaLocation,
        name: str,
        icon: Optional[str] = None,
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
    ):
        super().__init__(device, name, icon, uom, device_class, state_class)

    @property
    def device(self) -> MilaLocation:
        """Typed accessor (location-specific helpers like address.point.lat)."""
        return self._device  # type: ignore[return-value]
