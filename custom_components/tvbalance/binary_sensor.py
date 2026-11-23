"""Binary sensors: is the TV blocked, reachable, or waiting to be paired."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from tvbalance_client import Tv

from . import TVBalanceConfigEntry
from .coordinator import TVBalanceCoordinator
from .entity import TVBalanceEntity, add_entities_for_new_tvs


@dataclass(frozen=True, kw_only=True)
class TVBalanceBinarySensorDescription(BinarySensorEntityDescription):
    value: Callable[[Tv], bool]


BINARY_SENSORS: tuple[TVBalanceBinarySensorDescription, ...] = (
    TVBalanceBinarySensorDescription(
        key="blocked",
        value=lambda tv: bool(
            tv.status and tv.status.decision and tv.status.decision.kind == "block"
        ),
    ),
    TVBalanceBinarySensorDescription(
        key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda tv: bool(tv.status and tv.status.connected),
    ),
    TVBalanceBinarySensorDescription(
        key="needs_pairing",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda tv: tv.needs_pairing or bool(tv.status and tv.status.pairing_required),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TVBalanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    add_entities_for_new_tvs(
        entry,
        async_add_entities,
        lambda coordinator, tv_id: [
            TVBalanceBinarySensor(coordinator, tv_id, d) for d in BINARY_SENSORS
        ],
    )


class TVBalanceBinarySensor(TVBalanceEntity, BinarySensorEntity):
    entity_description: TVBalanceBinarySensorDescription

    def __init__(
        self,
        coordinator: TVBalanceCoordinator,
        tv_id: str,
        description: TVBalanceBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, tv_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        tv = self.tv
        return None if tv is None else self.entity_description.value(tv)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        tv = self.tv
        if self.entity_description.key != "blocked" or tv is None or not self.is_on:
            return None
        assert tv.status and tv.status.decision
        return {"reason": tv.status.decision.reason}
