"""Keeps the state of every TV: polled from the Engine and patched by its live event stream."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from tvbalance_client import (
    AdapterSummary,
    AuthenticationError,
    CertificateError,
    Event,
    Tv,
    TVBalanceClient,
    TVBalanceError,
    parse_status,
)

from .const import DOMAIN, EVENT_NAME

if TYPE_CHECKING:
    from . import TVBalanceConfigEntry

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=30)
RECONNECT_MIN = 1
RECONNECT_MAX = 60


def event_signal(entry_id: str, tv_id: str) -> str:
    """Dispatcher signal that carries the live events of one TV to its event entity."""
    return f"{DOMAIN}_{entry_id}_{tv_id}_event"


class TVBalanceCoordinator(DataUpdateCoordinator[dict[str, Tv]]):
    """TVs by id. The Engine is the source of truth; this only mirrors it."""

    config_entry: TVBalanceConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: TVBalanceConfigEntry, client: TVBalanceClient
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=POLL_INTERVAL
        )
        self.client = client
        self.adapters: dict[str, AdapterSummary] = {}

    async def _async_setup(self) -> None:
        try:
            self.adapters = {a.id: a for a in await self.client.adapters()}
        except (AuthenticationError, CertificateError) as ex:
            raise ConfigEntryAuthFailed(str(ex)) from ex
        except TVBalanceError as ex:
            raise UpdateFailed(str(ex)) from ex

    async def _async_update_data(self) -> dict[str, Tv]:
        try:
            tvs = await self.client.tvs()
        except (AuthenticationError, CertificateError) as ex:
            raise ConfigEntryAuthFailed(str(ex)) from ex
        except TVBalanceError as ex:
            raise UpdateFailed(str(ex)) from ex
        return {tv.id: tv for tv in tvs}

    def sync_devices(self) -> None:
        """Rename the device of a renamed TV and drop the device of a removed one."""
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            tv_id = next((i for domain, i in device.identifiers if domain == DOMAIN), None)
            if tv_id is None:
                continue
            tv = self.data.get(tv_id)
            if tv is None:
                registry.async_update_device(
                    device.id, remove_config_entry_id=self.config_entry.entry_id
                )
            elif device.name != tv.name:
                registry.async_update_device(device.id, name=tv.name)

    def start_listening(self) -> None:
        """Follow the Engine's live events until the entry unloads."""
        self.config_entry.async_create_background_task(
            self.hass, self._listen(), f"{DOMAIN} live events"
        )

    async def _listen(self) -> None:
        delay = RECONNECT_MIN
        while True:
            try:
                async for event in self.client.events():
                    delay = RECONNECT_MIN
                    self._handle(event)
            except (AuthenticationError, CertificateError):
                self.config_entry.async_start_reauth(self.hass)
                return
            except TVBalanceError as ex:
                _LOGGER.debug("Event stream lost: %s", ex)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    def _handle(self, event: Event) -> None:
        tv = self.data.get(event.tv_id) if event.tv_id else None
        if event.type == "status":
            if tv is None:
                self.config_entry.async_create_background_task(
                    self.hass, self.async_request_refresh(), f"{DOMAIN} refresh"
                )
                return
            patched = replace(tv, status=parse_status(event.payload))
            self.async_set_updated_data({**self.data, tv.id: patched})
            return

        device = None
        if tv is not None:
            device = next(
                (
                    d
                    for d in dr.async_entries_for_config_entry(
                        dr.async_get(self.hass), self.config_entry.entry_id
                    )
                    if (DOMAIN, tv.id) in d.identifiers
                ),
                None,
            )
        self.hass.bus.async_fire(
            EVENT_NAME,
            {
                "device_id": device.id if device else None,
                "tv_id": event.tv_id,
                "type": event.type,
                "payload": event.payload,
            },
        )
        if event.tv_id:
            async_dispatcher_send(
                self.hass, event_signal(self.config_entry.entry_id, event.tv_id), event
            )
        # Warnings, blocks and reachability change the picture: look again soon.
        self.config_entry.async_create_background_task(
            self.hass, self.async_request_refresh(), f"{DOMAIN} refresh"
        )
