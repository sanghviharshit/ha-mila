"""Device wrappers — one Python object per Home Assistant device.

A "device" here means an item in HA's device registry: an air purifier
or a household location. Each `MilaDevice` subclass:

* Reads its own slice of `coordinator.data` via dotted-path benedict
  access.
* Lazily builds the list of HA entities that belong to it.
* Provides the `DeviceInfo` block HA needs to group entities into a
  single card in the UI.

The split between devices and entities mirrors the split in HA's own
architecture: devices are organisational containers; entities are the
things users actually interact with.
"""
from .appliance import MilaAppliance
from .device import MilaDevice
from .location import MilaLocation

__all__ = ["MilaDevice", "MilaAppliance", "MilaLocation"]
