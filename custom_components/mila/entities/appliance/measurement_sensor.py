"""Sensor whose value comes from the appliance's `sensors[]` array.

Each appliance returns its environmental measurements as a list of
`{kind, latest: {instant, value}}` objects. We scan that list for the
configured `ApplianceSensorKind` and surface its latest value.

Most sensors use the value as-is. VOC is the one exception: the API
returns ppb, but HA's standard unit for VOC is `ug/m^3`, so we
multiply by `TVOC_PPB_TO_UGM3` in the device wrapper's entity list.
"""
from __future__ import annotations

from typing import List, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...api import ApplianceSensorKind
from ...const import DOMAIN
from ...devices import MilaAppliance
from .sensor import MilaApplianceSensor


class MilaApplianceMeasurementSensor(MilaApplianceSensor):
    """Maps one `ApplianceSensorKind` onto one HA sensor entity."""

    def __init__(
        self,
        device: MilaAppliance,
        name: str,
        sensor_kind: ApplianceSensorKind,
        icon: Optional[str] = None,
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        uom_conversion_factor: Optional[float] = None,
        precision: Optional[int] = None,
    ):
        # Every measurement is a MEASUREMENT-class sensor (continuous
        # numeric value sampled over time). We hardcode that here so
        # the device wrapper doesn't have to repeat it.
        super().__init__(device, name, icon, uom, device_class, SensorStateClass.MEASUREMENT)
        self._sensor_kind = sensor_kind
        self._uom_conversion_factor = uom_conversion_factor
        # `_attr_suggested_display_precision` lets the user override
        # the default formatting in their UI without having to define
        # a template sensor.
        self._attr_suggested_display_precision = precision

    @property
    def unique_id(self) -> str:
        """Stable id includes the sensor kind so each kind gets its own entity."""
        return f"{DOMAIN}_{self.device.id}_sensor_{self._sensor_kind}".lower()

    @property
    def native_value(self):
        """Return the latest reading for our `sensor_kind`, or None."""
        # `sensors` was populated by the coordinator from the
        # GET_APPLIANCES response. Each element looks like:
        #   {"kind": "Aqi", "latest": {"instant": ..., "value": 42.0}}
        sensors: List = self.device.get_value("sensors")
        sensor = next(
            (s for s in sensors if s["kind"] == self._sensor_kind), None
        )
        if sensor is None:
            return None
        value = sensor["latest"]["value"]
        # Apply the optional unit conversion (currently only VOC uses
        # this). Multiplying by None would be wrong, hence the guard.
        if self._uom_conversion_factor:
            return value * self._uom_conversion_factor
        return value
