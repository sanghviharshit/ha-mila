"""Device wrapper for a Mila account "location" (the household).

A location is a logical container for one or more appliances; it also
holds the nearest outdoor air-quality station and pollen station that
Mila chose for the user. We surface those as a HA device per location
so users can include them in dashboards alongside the appliances they
sit next to.

There's no write path on this side: location attributes are configured
through Mila's onboarding flow and don't change at runtime.
"""
from __future__ import annotations

import logging
from typing import List

from benedict import benedict
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..api import MilaApi
from .device import MilaDevice

_LOGGER = logging.getLogger(__name__)


class MilaLocation(MilaDevice):
    """Per-location wrapper (one per household in the account)."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: MilaApi,
        device_id: str,
    ) -> None:
        # `device_id` here is the coordinator-side "loc_<id>" key so
        # `id` collisions between appliances and locations are avoided.
        super().__init__(coordinator, api, device_id)

    @property
    def name(self) -> str:
        """Human label combining city, country, and id.

        The compound id at the end disambiguates multi-location
        accounts ("San Francisco, US (#5421)" vs another San Francisco
        entry). Falls back to the raw id when the address is missing
        from the payload (location removed from the account, or
        onboarding never set one) rather than rendering "None, None".
        """
        # Compose from whichever address parts exist so a payload with
        # only a city (or only a country) doesn't render a literal
        # "None" in the label.
        parts = [
            part
            for part in (
                self._device_data.get("address.city"),
                self._device_data.get("address.country"),
            )
            if part is not None
        ]
        if not parts:
            return f"Mila Location ({self.id})"
        return f"{', '.join(parts)} (#{self._device_data.get('id')})"

    @property
    def _device_data(self) -> benedict:
        """The slice of cached data that belongs to this location.

        Same disappeared-device tolerance as the appliance wrapper: an
        id missing from the latest payload yields an empty benedict so
        reads degrade to None instead of raising KeyError inside
        coordinator listener callbacks.
        """
        data = self._location_data.get(self.id)
        return benedict(data) if data is not None else benedict()

    def _get_model(self) -> str:
        """Locations are logical containers, not purifiers; say so on
        the device card instead of inheriting the appliance model."""
        return "Mila Location"

    def _get_all_entities(self) -> List[Entity]:
        """Build the per-location entity list.

        Deferred imports for the same circular-dependency reason as the
        appliance wrapper. Each entity is sensor-shaped (no controls
        for a location).
        """
        from ..entities import (
            MilaLocationAqiSensor,
            MilaLocationDistanceSensor,
            MilaLocationPathSensor,
        )

        return [
            # Static metadata about the chosen outdoor station.
            MilaLocationPathSensor(
                self, "Station Name", "outdoorStation.name", icon="mdi:map-marker"
            ),
            MilaLocationPathSensor(
                self,
                "Station Latitude",
                "outdoorStation.point.lat",
                icon="mdi:latitude",
            ),
            MilaLocationPathSensor(
                self,
                "Station Longitude",
                "outdoorStation.point.lon",
                icon="mdi:longitude",
            ),
            # Latest outdoor PM2.5 reading from that station.
            MilaLocationPathSensor(
                self,
                "Station PM2.5",
                "outdoorStation.sensor.latest.value",
                device_class=SensorDeviceClass.PM25,
                uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            # Only the pollen station's name is exposed. The old
            # `pollenStation.aggregateWindow[-1].*` daily-status sensors
            # were removed: `GET_LOCATIONS` never requests
            # `aggregateWindow`, so those five sensors were permanently
            # "unknown" for every account. If pollen data comes back,
            # add the field to the query first (and mind that its
            # response shape has historically been unstable), then
            # reintroduce the sensors.
            MilaLocationPathSensor(
                self,
                "Pollen Station Name",
                "pollenStation.name",
                icon="mdi:map-marker",
            ),
            # Derived sensors: AQI from PM2.5 and great-circle distance
            # between the household and the chosen outdoor station.
            MilaLocationAqiSensor(self),
            MilaLocationDistanceSensor(self),
        ]
