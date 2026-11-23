"""The activity event entity: what the Engine did or noticed for this TV."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from tvbalance_client import Event

from . import TVBalanceConfigEntry
from .coordinator import TVBalanceCoordinator, event_signal
from .entity import TVBalanceEntity, add_entities_for_new_tvs

EVENT_TYPES = [
    "time_warning",
    "blocked",
    "redirected",
    "powered_off",
    "enforcement_paused",
    "enforcement_unavailable",
    "tv_unreachable",
    "tv_reachable",
    "pairing_lost",
    "tv_paired",
    "profile_started",
    "profile_ended",
    "weekly_report",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TVBalanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    add_entities_for_new_tvs(
        entry,
        async_add_entities,
        lambda coordinator, tv_id: [TVBalanceActivity(coordinator, tv_id)],
    )


class TVBalanceActivity(TVBalanceEntity, EventEntity):
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator: TVBalanceCoordinator, tv_id: str) -> None:
        super().__init__(coordinator, tv_id, "activity")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                event_signal(self.coordinator.config_entry.entry_id, self.tv_id),
                self._on_event,
            )
        )

    @callback
    def _on_event(self, event: Event) -> None:
        if event.type not in EVENT_TYPES:
            return
        self._trigger_event(event.type, event.payload)
        self.async_write_ha_state()
