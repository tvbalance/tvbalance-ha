"""Sensors: what a TV is doing and how much of today's time is used."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from tvbalance_client import Tv

from . import TVBalanceConfigEntry
from .coordinator import TVBalanceCoordinator
from .entity import TVBalanceEntity, add_entities_for_new_tvs

PRESENCE_STATES = [
    "watching",
    "standby",
    "off",
    "unreachable",
    "needs_pairing",
    "not_monitored",
]


def presence(tv: Tv) -> str:
    """The same reading of a TV the web dashboard shows on its card."""
    if not tv.enabled:
        return "not_monitored"
    if tv.needs_pairing or (tv.status and tv.status.pairing_required):
        return "needs_pairing"
    if not tv.status or not tv.status.connected:
        return "unreachable"
    if tv.status.power in ("standby", "off"):
        return tv.status.power
    return "watching"


def _minutes(seconds: int | None) -> int | None:
    return None if seconds is None else round(seconds / 60)


@dataclass(frozen=True, kw_only=True)
class TVBalanceSensorDescription(SensorEntityDescription):
    value: Callable[[Tv], StateType]


SENSORS: tuple[TVBalanceSensorDescription, ...] = (
    TVBalanceSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=PRESENCE_STATES,
        value=presence,
    ),
    TVBalanceSensorDescription(
        key="app", value=lambda tv: tv.status.foreground_app if tv.status else None
    ),
    TVBalanceSensorDescription(
        key="input",
        entity_registry_enabled_default=False,
        value=lambda tv: tv.status.input_id if tv.status else None,
    ),
    TVBalanceSensorDescription(
        key="channel",
        entity_registry_enabled_default=False,
        value=lambda tv: tv.status.channel_id if tv.status else None,
    ),
    TVBalanceSensorDescription(
        key="program", value=lambda tv: tv.status.program_title if tv.status else None
    ),
    TVBalanceSensorDescription(
        key="profile",
        value=lambda tv: (
            tv.status.active_profile.name if tv.status and tv.status.active_profile else None
        ),
    ),
    TVBalanceSensorDescription(
        key="watched_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value=lambda tv: _minutes(tv.status.watched_seconds) if tv.status else None,
    ),
    TVBalanceSensorDescription(
        key="time_left",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value=lambda tv: _minutes(tv.status.remaining_seconds) if tv.status else None,
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
        lambda coordinator, tv_id: [TVBalanceSensor(coordinator, tv_id, d) for d in SENSORS],
    )


class TVBalanceSensor(TVBalanceEntity, SensorEntity):
    entity_description: TVBalanceSensorDescription

    def __init__(
        self,
        coordinator: TVBalanceCoordinator,
        tv_id: str,
        description: TVBalanceSensorDescription,
    ) -> None:
        super().__init__(coordinator, tv_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        tv = self.tv
        return None if tv is None else self.entity_description.value(tv)
