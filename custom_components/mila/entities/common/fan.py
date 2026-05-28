"""Base class for fan entities.

Currently only the per-appliance fan (`MilaApplianceFan`) extends this.
Lives in its own module to keep the inheritance chain clear and to
match the per-platform layout of the rest of `common/`.
"""
from __future__ import annotations

from typing import Optional

from homeassistant.components.fan import FanEntity

from ...devices import MilaDevice
from .entity import MilaEntity


class MilaFan(MilaEntity, FanEntity):
    """Mix-in of `MilaEntity` + HA's `FanEntity`.

    Subclasses fill in the actual fan-state plumbing (`percentage`,
    `preset_mode`, `async_set_percentage`, etc.). The base only sets
    the cosmetic bits (display name, icon).
    """

    def __init__(
        self,
        device: MilaDevice,
        name: str,
        icon: Optional[str] = None,
    ):
        super().__init__(device)
        # `_name` is the entity-local suffix appended to the device name
        # by the `name` property below. We keep it separate from the
        # device name so multiple entities on the same device get
        # different display labels without rewriting the device name.
        self._name = name
        self._attr_icon = icon

    @property
    def unique_id(self) -> str:
        """Subclass must override; HA enforces uniqueness across the install."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """Compose a friendly entity name from the device's label."""
        return f"{self.device.name_or_id} {self._name}"
