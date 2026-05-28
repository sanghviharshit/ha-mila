"""Shared appliance-sensor base.

`MilaApplianceSensor` only narrows the `device` property type to
`MilaAppliance`. Concrete sensor subclasses (`MilaAppliancePathSensor`,
`MilaApplianceMeasurementSensor`) live in sibling modules.
"""
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...devices import MilaAppliance
from ..common import MilaSensor

_LOGGER = logging.getLogger(__name__)


class MilaApplianceSensor(MilaSensor):
    """Base for every sensor that belongs to an air purifier."""

    def __init__(
        self,
        device: MilaAppliance,
        name: str,
        icon: Optional[str] = None,
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
    ):
        super().__init__(device, name, icon, uom, device_class, state_class)

    @property
    def device(self) -> MilaAppliance:
        """Typed accessor so subclasses can call appliance-specific helpers."""
        return self._device  # type: ignore[return-value]
