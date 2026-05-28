"""Great-circle distance from the household to its chosen outdoor station.

Mila picks the nearest outdoor air-quality station to populate its
PM2.5 readings, but the API doesn't tell us how far away it is. We
compute the geodesic distance locally using `geopy` so users can see
whether the station they're polling is two blocks away or twenty
miles.

We respect the HA instance's configured unit system: metric users see
kilometers, imperial users see miles.
"""
from __future__ import annotations

import logging
from typing import Optional

from geopy.distance import geodesic
from homeassistant.const import UnitOfLength
from homeassistant.util.unit_conversion import DistanceConverter
from homeassistant.util.unit_system import METRIC_SYSTEM

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

_LOGGER = logging.getLogger(__name__)


class MilaLocationDistanceSensor(MilaLocationSensor):
    """Distance between the household address and the outdoor station."""

    def __init__(self, device: MilaLocation):
        super().__init__(device, "Station Distance", "mdi:map-marker-distance")

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.device.id}_distance".lower()

    @property
    def native_value(self):
        """Compute the distance and return it in the user's preferred unit.

        `geodesic(...).km` always returns kilometres. We only convert
        when the HA instance is using the imperial system; otherwise
        we leave the value as-is so HA's metric unit handling is
        consistent.
        """
        try:
            location_point = (
                float(self.device.get_value("address.point.lat")),
                float(self.device.get_value("address.point.lon")),
            )
            station_point = (
                float(self.device.get_value("outdoorStation.point.lat")),
                float(self.device.get_value("outdoorStation.point.lon")),
            )

            val = geodesic(location_point, station_point).km
            if not self._is_metric:
                val = DistanceConverter.convert(
                    val, UnitOfLength.KILOMETERS, UnitOfLength.MILES
                )

            # Two decimal places matches the precision of Mila's own
            # nearest-station UI.
            return round(val, 2)
        except Exception as ex:
            _LOGGER.error(
                "Error getting native value for %s", self.name, exc_info=ex
            )
            return None

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        """Report km or mi based on the user's HA unit preference."""
        return UnitOfLength.KILOMETERS if self._is_metric else UnitOfLength.MILES

    @property
    def _is_metric(self) -> bool:
        """True if the HA instance is set to metric units."""
        return self.device.hass.config.units is METRIC_SYSTEM
