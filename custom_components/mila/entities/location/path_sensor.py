"""Location sensor that reads one dotted path from cached location data.

Same idea as `MilaAppliancePathSensor`, but for the location wrapper.
Most of the location-side sensors (station name, lat/lon, pollen
status) are thin wrappers over this class.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...const import DOMAIN
from ...devices import MilaLocation
from .sensor import MilaLocationSensor

_LOGGER = logging.getLogger(__name__)


class MilaLocationPathSensor(MilaLocationSensor):
    """Sensor whose value is the result of a dotted-path lookup on location data."""

    def __init__(
        self,
        device: MilaLocation,
        name: str,
        data_path: str,
        icon: Optional[str] = None,
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
        convert_function: Optional[Callable] = None,
    ):
        super().__init__(device, name, icon, uom, device_class, state_class)
        self._data_path = data_path
        self._convert_function = convert_function

    @property
    def unique_id(self) -> str:
        """Stable id derived from location id + the data path."""
        return f"{DOMAIN}_{self.device.id}_{self._data_path.replace('.', '_')}".lower()

    @property
    def native_value(self):
        """Look up the path; convert if requested."""
        try:
            val = self.device.get_value(self._data_path)
            if self._convert_function is not None:
                val = self._convert_function(val)
            return val
        except KeyError:
            # Missing path -> report None. Common for pollen fields on
            # accounts without nearby pollen stations.
            return None
        except Exception as ex:
            _LOGGER.error(
                "Error getting native value for %s", self.name, exc_info=ex
            )
            return None
