"""Shared base for the entities of one TV, and the "add entities for new TVs" helper."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from tvbalance_client import Tv

from . import TVBalanceConfigEntry
from .const import DOMAIN
from .coordinator import TVBalanceCoordinator


class TVBalanceEntity(CoordinatorEntity[TVBalanceCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: TVBalanceCoordinator, tv_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.tv_id = tv_id
        self._attr_unique_id = f"{tv_id}_{key}"
        self._attr_translation_key = key
        tv = coordinator.data[tv_id]
        adapter = coordinator.adapters.get(tv.adapter_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, tv_id)},
            name=tv.name,
            manufacturer=adapter.brand if adapter else None,
            model=adapter.display_name if adapter else tv.adapter_id,
        )

    @property
    def tv(self) -> Tv | None:
        return self.coordinator.data.get(self.tv_id)

    @property
    def available(self) -> bool:
        return super().available and self.tv is not None


def add_entities_for_new_tvs(
    entry: TVBalanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    build: Callable[[TVBalanceCoordinator, str], list[Entity]],
) -> None:
    """Add the entities of every TV now, and of each TV the Engine gains later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    def add_new() -> None:
        fresh = set(coordinator.data) - known
        if not fresh:
            return
        known.update(fresh)
        async_add_entities([e for tv_id in sorted(fresh) for e in build(coordinator, tv_id)])

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))
