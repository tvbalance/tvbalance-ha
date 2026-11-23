"""Services that grant time or change enforcement. They need a Home Assistant administrator.

Automations and blueprints still call them: they run without a user. No PIN is ever involved; the
Engine only sees the integration's API token.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .coordinator import TVBalanceCoordinator
from .errors import engine_call

ATTR_DEVICE_ID = "device_id"
MAX_MINUTES = 24 * 60

DEVICE = {vol.Required(ATTR_DEVICE_ID): cv.string}
MINUTES = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_MINUTES))
DURATION = {
    vol.Optional("minutes"): MINUTES,
    vol.Optional("until_midnight", default=False): cv.boolean,
}

type Handler = Callable[[TVBalanceCoordinator, str, ServiceCall], Awaitable[object]]


def _invalid(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def _resolve(hass: HomeAssistant, device_id: str) -> tuple[TVBalanceCoordinator, str]:
    """The coordinator and Engine TV id behind a Home Assistant device."""
    device = dr.async_get(hass).async_get(device_id)
    tv_id = (
        next((i for domain, i in device.identifiers if domain == DOMAIN), None) if device else None
    )
    if device is None or tv_id is None:
        raise _invalid("unknown_device")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data, tv_id
    raise _invalid("entry_not_loaded")


def _household(hass: HomeAssistant) -> TVBalanceCoordinator:
    """The coordinator of the loaded Engine: profiles belong to the household, not to a TV."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    raise _invalid("entry_not_loaded")


def _duration(call: ServiceCall) -> dict[str, Any]:
    minutes, until_midnight = call.data.get("minutes"), call.data["until_midnight"]
    if (minutes is None) == (not until_midnight):
        raise _invalid("choose_one_duration")
    return {"minutes": minutes, "until_midnight": until_midnight}


async def _bonus(c: TVBalanceCoordinator, tv_id: str, call: ServiceCall) -> object:
    return await engine_call(c.client.bonus(tv_id, call.data["minutes"]))


async def _allow(c: TVBalanceCoordinator, tv_id: str, call: ServiceCall) -> object:
    return await engine_call(c.client.override(tv_id, allow=True, **_duration(call)))


async def _block(c: TVBalanceCoordinator, tv_id: str, call: ServiceCall) -> object:
    return await engine_call(c.client.override(tv_id, allow=False, **_duration(call)))


async def _pause(c: TVBalanceCoordinator, tv_id: str, call: ServiceCall) -> object:
    return await engine_call(c.client.pause(tv_id, call.data["minutes"]))


async def _clear_override(c: TVBalanceCoordinator, tv_id: str, call: ServiceCall) -> object:
    return await engine_call(c.client.clear_override(tv_id))


async def _set_monitoring(c: TVBalanceCoordinator, tv_id: str, call: ServiceCall) -> object:
    return await engine_call(c.client.update_tv(tv_id, enabled=call.data["enabled"]))


PROFILE_ACTIVATE = vol.Schema(
    {
        vol.Required("policy_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("excluded_device_ids", default=list): [cv.string],
        **DURATION,
    }
)


SERVICES: dict[str, tuple[Handler, vol.Schema]] = {
    "bonus": (_bonus, vol.Schema({**DEVICE, vol.Required("minutes"): MINUTES})),
    "allow": (_allow, vol.Schema({**DEVICE, **DURATION})),
    "block": (_block, vol.Schema({**DEVICE, **DURATION})),
    "pause": (_pause, vol.Schema({**DEVICE, vol.Optional("minutes", default=30): MINUTES})),
    "clear_override": (_clear_override, vol.Schema(DEVICE)),
    "set_monitoring": (
        _set_monitoring,
        vol.Schema({**DEVICE, vol.Required("enabled"): cv.boolean}),
    ),
}


def async_setup_services(hass: HomeAssistant) -> None:
    async def activate_profile(call: ServiceCall) -> None:
        coordinator = _household(hass)
        excluded = [_resolve(hass, device_id)[1] for device_id in call.data["excluded_device_ids"]]
        await engine_call(
            coordinator.client.activate_profile(
                call.data["policy_id"], excluded_tv_ids=excluded, **_duration(call)
            )
        )
        await coordinator.async_request_refresh()

    async def stop_profile(call: ServiceCall) -> None:
        coordinator = _household(hass)
        await engine_call(coordinator.client.stop_profile())
        await coordinator.async_request_refresh()

    async_register_admin_service(
        hass, DOMAIN, "activate_profile", activate_profile, PROFILE_ACTIVATE
    )
    async_register_admin_service(hass, DOMAIN, "stop_profile", stop_profile, vol.Schema({}))

    for name, (handler, schema) in SERVICES.items():

        async def run(call: ServiceCall, handler: Handler = handler) -> None:
            coordinator, tv_id = _resolve(hass, call.data[ATTR_DEVICE_ID])
            await handler(coordinator, tv_id, call)
            await coordinator.async_request_refresh()

        async_register_admin_service(hass, DOMAIN, name, run, schema)
