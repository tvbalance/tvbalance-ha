"""Builds the client for an Engine, pinning its local CA when there is one."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from tvbalance_client import TVBalanceClient, ssl_context_for


async def build_client(
    hass: HomeAssistant, url: str, token: str | None, ca_pem: str | None = None
) -> TVBalanceClient:
    # Loading a CA reads the SSL library's trust store API, so it stays off the event loop.
    context = await hass.async_add_executor_job(ssl_context_for, ca_pem) if ca_pem else None
    return TVBalanceClient(url, token, session=async_get_clientsession(hass), ssl_context=context)
