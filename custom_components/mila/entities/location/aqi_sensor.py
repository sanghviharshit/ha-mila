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
        # A missing reading (no station near this account, or the
        # location dropped out of the payload) is a routine condition:
        # report "unknown" quietly. Logging it at ERROR level would
        # spam the log on every poll for affected accounts.
        pm25 = self.device.get_value("outdoorStation.sensor.latest.value")
        if pm25 is None:
            return None
        try:
            # `to_iaqi` expects the concentration as a string (it uses
            # arbitrary-precision Decimal under the hood) and returns
            # another string; we cast both ends to play nicely.
            return float(
                aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm25), algo=aqi.ALGO_EPA)
            )
        except Exception as ex:
            # python-aqi can raise on out-of-range / non-numeric inputs
            # (e.g. a wildfire reading beyond the EPA table). Still a
            # per-poll condition, so keep it out of the error log; the
            # entity shows "unknown" and debug logging has the details.
            _LOGGER.debug(
                "Could not compute AQI for %s from PM2.5 value %r: %s",
                self.name,
                pm25,
                ex,
            )
            return None
