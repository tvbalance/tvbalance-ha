"""TVBalance: thin Home Assistant integration over the TVBalance Engine API."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from tvbalance_client import CertificateError, TVBalanceError

from .connection import build_client
from .const import CONF_CA_PEM, CONF_TOKEN, CONF_URL, DOMAIN
from .coordinator import TVBalanceCoordinator
from .services import async_setup_services

type TVBalanceConfigEntry = ConfigEntry[TVBalanceCoordinator]

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TVBalanceConfigEntry) -> bool:
    client = await build_client(
        hass, entry.data[CONF_URL], entry.data.get(CONF_TOKEN), entry.data.get(CONF_CA_PEM)
    )
    try:
        await client.health()
    except CertificateError as ex:
        raise ConfigEntryAuthFailed(f"TVBalance certificate no longer trusted: {ex}") from ex
    except TVBalanceError as ex:
        raise ConfigEntryNotReady(f"TVBalance Engine unavailable: {ex}") from ex
    coordinator = TVBalanceCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_add_listener(coordinator.sync_devices))
    coordinator.start_listening()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TVBalanceConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
