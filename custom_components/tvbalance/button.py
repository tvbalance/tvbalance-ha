"""The Pause button: stop enforcement for a while. Harmless, so any user may press it."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TVBalanceConfigEntry
from .coordinator import TVBalanceCoordinator
from .entity import TVBalanceEntity, add_entities_for_new_tvs
from .errors import engine_call

PAUSE_MINUTES = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TVBalanceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    add_entities_for_new_tvs(
        entry,
        async_add_entities,
        lambda coordinator, tv_id: [TVBalancePauseButton(coordinator, tv_id)],
    )


class TVBalancePauseButton(TVBalanceEntity, ButtonEntity):
    def __init__(self, coordinator: TVBalanceCoordinator, tv_id: str) -> None:
        super().__init__(coordinator, tv_id, "pause")

    async def async_press(self) -> None:
        await engine_call(self.coordinator.client.pause(self.tv_id, PAUSE_MINUTES))
        await self.coordinator.async_request_refresh()
