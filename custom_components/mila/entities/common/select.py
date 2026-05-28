"""Base class for Mila select (dropdown) entities.

Currently the only subclass is `MilaSoundModeSelect`, which exposes the
SoundsConfig enum (`Enabled` / `DaytimeOnly` / `Disabled`).
"""
from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.select import SelectEntity

from ...devices import MilaDevice
from .entity import MilaEntity


class MilaSelect(MilaEntity, SelectEntity):
    """`MilaEntity` + `SelectEntity` — subclasses define options + current value."""

    def __init__(
        self,
        device: MilaDevice,
        name: str,
        icon: Optional[str] = None,
    ):
        super().__init__(device)
        self._name = name
        self._attr_icon = icon

    @property
    def unique_id(self) -> str:
        """Subclass-defined stable id."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """Compose device name + entity-local suffix."""
        return f"{self.device.name_or_id} {self._name}"

    @property
    def options(self) -> list[str]:
        """List of selectable values (the dropdown items)."""
        raise NotImplementedError

    @property
    def current_option(self) -> Optional[str]:
        """Which option is currently selected (or None if unknown)."""
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        """Persist the user's choice to the API."""
        raise NotImplementedError
