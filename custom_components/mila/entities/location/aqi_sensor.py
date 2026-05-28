"""AQI sensor derived from the outdoor station's PM2.5 reading.

Mila's API gives us raw PM2.5 (micrograms per cubic meter) but not an
AQI value. We compute AQI locally using `python-aqi` and the EPA
breakpoint table so users see the familiar 0-500 number rather than a
raw concentration.
"""
from __future__ import annotations

import logging

import aqi
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

_LOGGER = logging.getLogger(__name__)


class MilaLocationAqiSensor(MilaLocationSensor):
    """Outdoor AQI computed from the closest station's PM2.5 reading."""

    def __init__(self, device: MilaLocation):
        super().__init__(
            device,
            "AQI",
            device_class=SensorDeviceClass.AQI,
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_aqi".lower()

    @property
    def native_value(self):
        """Convert the cached PM2.5 ug/m^3 reading into an EPA AQI value."""
        pm25 = self.device.get_value("outdoorStation.sensor.latest.value")
        try:
            # `to_iaqi` expects the concentration as a string (it uses
            # arbitrary-precision Decimal under the hood) and returns
            # another string; we cast both ends to play nicely.
            return float(
                aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm25), algo=aqi.ALGO_EPA)
            )
        except Exception as ex:
            # python-aqi can raise on out-of-range / non-numeric inputs.
            # Log but surface None so the entity goes "unknown" rather
            # than disappearing from HA's UI.
            _LOGGER.error(
                "Error getting native value for %s", self.name, exc_info=ex
            )
            return None
