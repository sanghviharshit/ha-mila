"""Base class for every Mila "device" (appliance + location).

The class hierarchy is intentionally shallow:

    MilaDevice              <-- abstract base, in this file
      ├── MilaAppliance     <-- one per Mila air purifier
      └── MilaLocation      <-- one per Mila account location

A `MilaDevice` instance pools the things every device needs: a reference
to the coordinator, helpers to walk the cached data via dotted paths, a
HA `DeviceInfo` builder, and a place to stash the entity list that
platforms will read.

We use `python-benedict` for the dotted-path lookups (`room.kind`,
`state.firmware.version`, etc.). It's a thin convenience over plain
dicts; the alternative is half a dozen `.get(...).get(...)` chains per
attribute.
"""
from __future__ import annotations

from typing import List

from benedict import benedict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import (
    CALLBACK_TYPE,
    DataUpdateCoordinator,
)

from ..api import MilaApi
from ..const import (
    DATAKEY_ACCOUNT,
    DATAKEY_APPLIANCE,
    DATAKEY_LOCATION,
    DOMAIN,
    MANUFACTURER,
)


class MilaDevice:
    """Abstract base shared by all per-device wrappers.

    Concrete subclasses override:

    * `name`              — human-readable label.
    * `_device_data`      — the slice of coordinator data for this device.
    * `_get_all_entities` — entity list for HA platforms.
    * `_get_software_version` — firmware string for `DeviceInfo`.
    """

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: MilaApi,
        device_id: str,
    ) -> None:
        """Stash the coordinator and API, then build the entity list.

        Building the entity list eagerly (rather than on first access)
        means platforms can iterate `.entities` without worrying about
        race conditions: by the time `_get_all_entities` runs, the
        first coordinator refresh has already populated cached data.
        """
        self._id = device_id
        self._hass = coordinator.hass
        self._coordinator = coordinator
        self._api = api
        # Keyed by `unique_id` to make `_build_entities_list` idempotent
        # if it's ever called twice for the same device.
        self._entities: dict[str, Entity] = {}
        self._build_entities_list()

    # ----- Plain accessors --------------------------------------------

    @property
    def hass(self) -> HomeAssistant:
        """The HA core object; used by entities for unit-system lookups, etc."""
        return self._hass

    @property
    def id(self) -> str:
        """Stable identifier for this device.

        For appliances this is the MAC-address-derived id Mila assigns
        (e.g. `48ca439d0dbc`). For locations it's the prefixed string
        the coordinator uses (`loc_<location_id>`).
        """
        return self._id

    @property
    def name(self) -> str:
        """Human-readable label. Subclasses must override."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Whether the device should appear available in HA.

        Default is True; appliances override to mark themselves
        unavailable when the API reports `actualMode = null` (offline).
        """
        return True

    @property
    def name_or_id(self) -> str:
        """`name` if set, otherwise `id`.

        Useful when building entity names: a freshly added appliance
        might not have a user-supplied name yet, and falling back to
        the raw id keeps logs readable instead of showing "None Fan".
        """
        return self.name if self.name is not None else self.id

    @property
    def entities(self) -> list[Entity]:
        """The flat list of HA entities this device owns."""
        return list(self._entities.values())

    @property
    def device_info(self) -> DeviceInfo:
        """Build the `DeviceInfo` HA uses for the device card.

        `identifiers` is the key HA uses to dedupe devices; we tag
        every entity with `(DOMAIN, self.id)` so HA groups them into a
        single card.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self.id)},
            manufacturer=MANUFACTURER,
            model=self._get_model(),
            name=self.name,
            # Empty string would render as a blank field on the device
            # card; None makes HA omit the row entirely.
            sw_version=self._get_software_version() or None,
        )

    # ----- Coordinator-data accessors ---------------------------------
    #
    # The coordinator caches three top-level dicts; we wrap each in a
    # benedict so subclasses can use dotted-path access.

    @property
    def _appliance_data(self) -> benedict:
        """Every appliance the account owns, keyed by id.

        `coordinator.data` is None until the first refresh assigns it;
        devices are constructed *during* that refresh, so tolerate the
        None here rather than trusting call order.
        """
        return benedict((self._coordinator.data or {}).get(DATAKEY_APPLIANCE) or {})

    @property
    def _account_data(self) -> benedict:
        """Owner profile (email + name). Fetched on the first refresh and
        carried forward by the coordinator on every later poll."""
        return benedict((self._coordinator.data or {}).get(DATAKEY_ACCOUNT) or {})

    @property
    def _location_data(self) -> benedict:
        """Every location, keyed by `loc_<id>` (matching the coordinator)."""
        return benedict((self._coordinator.data or {}).get(DATAKEY_LOCATION) or {})

    @property
    def _device_data(self) -> benedict:
        """The single-device sub-payload. Subclasses define which dict to read."""
        raise NotImplementedError

    def get_value(self, data_path: str):
        """Read a dotted-path value out of this device's data.

        Returns `None` if any segment along the path is missing or null.
        This None contract is what lets entity properties read cached
        data without try/except at every call site: a payload that lost
        a branch (offline appliance, account change) degrades to
        "unknown" state instead of a KeyError aborting the entity's
        state write. Note that benedict's `[]` indexing raises on
        missing paths; `.get` is the spelling that honours the contract.
        """
        return self._device_data.get(data_path)

    def add_update_listener(self, callback: CALLBACK_TYPE):
        """Subscribe a callback to coordinator updates.

        Wraps `coordinator.async_add_listener` so callers (entities)
        don't need to reach through the device to the coordinator.
        Used by `MilaApplianceFan` to clear its optimistic
        percentage-override once a real reading lands.
        """
        self._coordinator.async_add_listener(callback)

    # ----- Subclass hooks ---------------------------------------------

    def _build_entities_list(self) -> None:
        """Run `_get_all_entities` and deduplicate by `unique_id`.

        Deduplication matters because a future change might cause the
        same entity to appear twice (e.g. if a subclass forgets that
        the base class already adds it). HA throws on duplicate
        unique_ids, so catching it here keeps the error contained.

        Imports `MilaEntity` lazily to avoid a circular dependency:
        entities import devices, devices import entities here only
        when actually building.
        """
        from ..entities import MilaEntity

        for entity in self._get_all_entities():
            if not isinstance(entity, MilaEntity):
                continue
            if entity.unique_id not in self._entities:
                self._entities[entity.unique_id] = entity

    def _get_all_entities(self) -> List[Entity]:
        """Return the per-device entity list. Subclasses override."""
        return []

    def _get_software_version(self) -> str:
        """Firmware version string for `DeviceInfo`. Default: empty."""
        return ""

    def _get_model(self) -> str:
        """Model string for `DeviceInfo`.

        Defaults to the purifier because that's the common case;
        non-appliance subclasses (locations) override so they don't
        register in HA's device registry as air purifiers.
        """
        return "Mila Air Purifier"
