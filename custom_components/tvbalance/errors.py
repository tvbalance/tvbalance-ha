"""Turns Engine failures into translated Home Assistant errors."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError

from tvbalance_client import AuthenticationError, TVBalanceError

from .const import DOMAIN


async def engine_call[T](call: Awaitable[T]) -> T:
    """Await an Engine call; a refusal says which token scope is missing."""
    try:
        return await call
    except AuthenticationError as ex:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="not_allowed",
            translation_placeholders={"error": str(ex)},
        ) from ex
    except TVBalanceError as ex:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="engine_error",
            translation_placeholders={"error": str(ex)},
        ) from ex
