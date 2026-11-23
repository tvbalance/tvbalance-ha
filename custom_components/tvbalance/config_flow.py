"""Config flow: connect to a TVBalance Engine by URL and API token."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from tvbalance_client import (
    AuthenticationError,
    CertificateError,
    TVBalanceConnectionError,
    TVBalanceError,
    ca_fingerprint,
    fetch_ca_certificate,
)

from .connection import build_client
from .const import CONF_CA_PEM, CONF_TOKEN, CONF_URL, DOMAIN


class TVBalanceConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _discovered: tuple[str, str] | None = None  # (url, token) announced by the Add-on
    _pending: tuple[str, str, str] | None = None  # (url, token, CA) waiting for the fingerprint

    async def _check(self, url: str, token: str, ca_pem: str | None = None) -> str | None:
        """Return the error key, or None when this Engine accepts the token."""
        client = await build_client(self.hass, url, token, ca_pem)
        try:
            await client.info()  # public: is this an Engine at all?
            await client.tvs()  # authenticated: is the token accepted?
        except CertificateError:
            return "untrusted_certificate"
        except TVBalanceConnectionError:
            return "cannot_connect"
        except AuthenticationError:
            return "invalid_auth"
        except TVBalanceError:
            return "invalid_response"
        return None

    async def _probe(self, url: str, ca_pem: str) -> str | None:
        """Whether the Engine answers over TLS with this CA (no sign-in: reauth may be for that)."""
        try:
            await (await build_client(self.hass, url, None, ca_pem)).health()
        except CertificateError:
            return "untrusted_certificate"
        except TVBalanceError:
            return "cannot_connect"
        return None

    async def _fetch_ca(self, url: str) -> str | None:
        """The CA an Engine offers, or None when it has none (a certificate of the user's own)."""
        try:
            pem = await fetch_ca_certificate(url, async_get_clientsession(self.hass))
            ca_fingerprint(pem)
        except (TVBalanceError, ValueError):
            return None
        return pem

    async def _confirm_ca(self, url: str, token: str) -> ConfigFlowResult | None:
        """Show the CA's fingerprint, or None when there is no CA to show."""
        if (pem := await self._fetch_ca(url)) is None:
            return None
        self._pending = (url, token, pem)
        return await self.async_step_tls_confirm()

    async def _create(self, url: str, token: str, ca_pem: str | None) -> ConfigFlowResult:
        await self.async_set_unique_id(url)
        self._abort_if_unique_id_configured()
        data = {CONF_URL: url, CONF_TOKEN: token}
        if ca_pem:
            data[CONF_CA_PEM] = ca_pem
        return self.async_create_entry(title=f"TVBalance ({url})", data=data)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            token = user_input[CONF_TOKEN].strip()
            error = await self._check(url, token)
            if error == "untrusted_certificate" and (shown := await self._confirm_ca(url, token)):
                return shown
            if error:
                errors["base"] = error
            else:
                return await self._create(url, token, None)

        schema = vol.Schema({vol.Required(CONF_URL): str, vol.Required(CONF_TOKEN): str})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_tls_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The user compares the CA's fingerprint with the one in the Engine's settings."""
        assert self._pending is not None
        url, token, pem = self._pending
        errors: dict[str, str] = {}
        if user_input is not None:
            reauth = self.source == SOURCE_REAUTH
            if error := await (self._probe(url, pem) if reauth else self._check(url, token, pem)):
                errors["base"] = error
            elif reauth:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_CA_PEM: pem}
                )
            else:
                return await self._create(url, token, pem)
        return self.async_show_form(
            step_id="tls_confirm",
            errors=errors,
            description_placeholders={"url": url, "fingerprint": ca_fingerprint(pem)},
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        config = discovery_info.config
        host, port, token = config.get("host"), config.get("port"), config.get("token")
        if not (host and port and token):
            return self.async_abort(reason="invalid_discovery")
        url = f"http://{host}:{port}"
        await self.async_set_unique_id(url)
        # A fresh token (the old one was revoked) refreshes the entry instead of asking again.
        self._abort_if_unique_id_configured(updates={CONF_TOKEN: token}, reload_on_update=True)
        self._discovered = (url, str(token))
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        url, token = self._discovered
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._check(url, token):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="TVBalance (Add-on)", data={CONF_URL: url, CONF_TOKEN: token}
                )
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        url, token = entry_data[CONF_URL], entry_data.get(CONF_TOKEN, "")
        if url.startswith("https://"):
            client = await build_client(self.hass, url, None, entry_data.get(CONF_CA_PEM))
            try:
                await client.health()
            except CertificateError:  # the Engine made a new CA: the user confirms it again
                if shown := await self._confirm_ca(url, token):
                    return shown
            except TVBalanceError:
                pass  # not a certificate matter: the token step tells what is wrong
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            client = await build_client(
                self.hass, entry.data[CONF_URL], token, entry.data.get(CONF_CA_PEM)
            )
            try:
                await client.tvs()
            except TVBalanceConnectionError:
                errors["base"] = "cannot_connect"
            except CertificateError:
                errors["base"] = "untrusted_certificate"
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except TVBalanceError:
                errors["base"] = "invalid_response"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )
