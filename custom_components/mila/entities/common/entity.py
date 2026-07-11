"""Root base class for every Mila entity.

`MilaEntity` glues an entity to the coordinator (so HA automatically
refreshes it whenever the coordinator's data updates) and provides the
`device_info` block HA needs to group entities into a single device
card.

Subclasses must still fill in `unique_id` and `name`. The coordinator
linkage is set up by `CoordinatorEntity` (the upstream HA helper); we
just route the right coordinator into it via the wrapped device.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import ATTRIBUTION
from ...devices import MilaDevice


class MilaEntity(CoordinatorEntity):
    """Base for every entity in the integration.

    Storing the `MilaDevice` reference (rather than just the
    coordinator) gives subclasses easy access to dotted-path data
    helpers (`device.get_value("room.kind")`) and the device's
    `DeviceInfo` block.
    """

    # Shown by HA under each entity's "Attribution" attribute so users
    # can see where the data ultimately comes from.
    _attr_attribution = ATTRIBUTION

    def __init__(self, device: MilaDevice):
        # `CoordinatorEntity.__init__` registers an internal listener
        # that calls `async_write_ha_state` whenever the coordinator
        # gets fresh data, so subclasses don't have to.
        super().__init__(device._coordinator)
        self._device = device

    @property
    def device(self) -> MilaDevice:
        """The device this entity belongs to. Subclasses use it for data lookups."""
        return self._device

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Forward to the device wrapper so HA can group entities by device."""
        return self.device.device_info

    @property
    def unique_id(self) -> str:
        """Stable per-entity id. Subclasses must override."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """User-visible label. Subclasses must override."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Combine cloud reachability with per-device availability.

        `CoordinatorEntity.available` (the `super()` term) reflects
        whether the most recent coordinator poll succeeded. Dropping it
        would leave entities showing frozen stale values as if live
        whenever the Mila cloud is unreachable. The device layer then
        adds its own signal: an appliance reporting
        `state.actualMode = null` is offline even when the cloud is up,
        and a single offline appliance greys out every one of its
        entities consistently.
        """
        return super().available and self.device.available
