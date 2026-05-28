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
        entry).
        """
        return (
            f"{self._device_data['address.city']}, "
            f"{self._device_data['address.country']} "
            f"(#{self._device_data['id']})"
        )

    @property
    def _device_data(self) -> benedict:
        """The slice of cached data that belongs to this location."""
        return self._location_data[self.id]

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
            # The pollen station name is included; the live API does
            # return aggregateWindow but its shape is brittle (the
            # `aggregateWindow[-1].status.*` paths below historically
            # rendered empty on many accounts). We expose the path
            # sensors so users with valid data see them, and pollen-free
            # accounts simply get `None` for the daily values.
            MilaLocationPathSensor(
                self,
                "Pollen Station Name",
                "pollenStation.name",
                icon="mdi:map-marker",
            ),
            MilaLocationPathSensor(
                self,
                "Pollen Reported Date",
                "pollenStation.aggregateWindow[-1].date",
                device_class=SensorDeviceClass.DATE,
            ),
            MilaLocationPathSensor(
                self,
                "Pollen Status - Trees",
                "pollenStation.aggregateWindow[-1].status.trees",
                icon="mdi:tree",
            ),
            MilaLocationPathSensor(
                self,
                "Pollen Status - Weeds",
                "pollenStation.aggregateWindow[-1].status.weeds",
                icon="mdi:flower",
            ),
            MilaLocationPathSensor(
                self,
                "Pollen Status - Grass",
                "pollenStation.aggregateWindow[-1].status.grass",
                icon="mdi:grass",
            ),
            MilaLocationPathSensor(
                self,
                "Pollen Status - Mold",
                "pollenStation.aggregateWindow[-1].status.mold",
                icon="mdi:mushroom",
            ),
            # Derived sensors: AQI from PM2.5 and great-circle distance
            # between the household and the chosen outdoor station.
            MilaLocationAqiSensor(self),
            MilaLocationDistanceSensor(self),
        ]
