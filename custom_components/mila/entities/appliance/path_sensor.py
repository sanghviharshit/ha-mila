"""Generic appliance sensor that reads a single dotted path from cached data.

This is the workhorse for most of the appliance sensors. The wrapped
device exposes a `get_value("a.b.c")` helper backed by benedict; this
class simply forwards a fixed path and optionally runs a converter on
the result before HA reads it.

Used for things like:

* `state.actualMode`        -> stringified enum value
* `state.wifiRssi`          -> integer signal strength
* `filter.installedAt`      -> tz-aware UTC datetime (via `_to_utc`)
* `room.bedtime.localStart` -> "HH:MM:SS" string

If the path is missing in the payload the sensor reports `None`, which
HA renders as `unknown` in the UI.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...const import DOMAIN
from ...devices import MilaAppliance
from .sensor import MilaApplianceSensor

_LOGGER = logging.getLogger(__name__)


class MilaAppliancePathSensor(MilaApplianceSensor):
    """Sensor whose value is the result of a dotted-path lookup on appliance data."""

    def __init__(
        self,
        device: MilaAppliance,
        name: str,
        data_path: str,
        icon: Optional[str] = None,
        uom: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
        convert_function: Optional[Callable] = None,
    ):
        super().__init__(device, name, icon, uom, device_class, state_class)
        # Stored verbatim — `MilaDevice.get_value` accepts the same
        # dotted syntax that benedict uses.
        self._data_path = data_path
        # Optional post-processor (e.g. stringify an enum, attach UTC to
        # a naive datetime). Called only when the raw value is found.
        self._convert_function = convert_function

    @property
    def unique_id(self) -> str:
        """Stable id derived from domain + appliance id + data path.

        Dots in the path become underscores so the resulting id is a
        valid HA entity id segment.
        """
        return f"{DOMAIN}_{self.device.id}_{self._data_path.replace('.', '_')}".lower()

    @property
    def native_value(self):
        """Read + (optionally) convert the value at the configured path."""
        try:
            val = self.device.get_value(self._data_path)
            if self._convert_function is not None:
                val = self._convert_function(val)
            return val
        except KeyError:
            # benedict raises KeyError for missing paths; that's
            # expected on a fresh setup (e.g. filter dates before the
            # appliance reports them). Surface as `None` so HA renders
            # it as "unknown" rather than logging an error.
            return None
        except Exception as ex:
            # Anything else is unexpected. Log with traceback so the
            # user can file an issue without us silently dropping data.
            _LOGGER.error(
                "Error getting native value for %s", self.name, exc_info=ex
            )
            return None
