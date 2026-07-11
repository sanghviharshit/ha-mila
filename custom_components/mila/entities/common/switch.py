"""Base class for Mila switch (toggle) entities.

Subclassed by the smart-mode toggles. Each smart mode (Quiet, Sleep,
Whitenoise, ...) becomes one switch on each appliance.
"""
from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.switch import SwitchEntity

from ...devices import MilaDevice
from .entity import MilaEntity


class MilaSwitch(MilaEntity, SwitchEntity):
    """`MilaEntity` + `SwitchEntity` — subclasses provide is_on + turn on/off."""

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
    def is_on(self) -> bool:
        """Current state. May return None when state is still unknown."""
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Persist the on state to the API."""
        raise NotImplementedError

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Persist the off state to the API."""
        raise NotImplementedError
