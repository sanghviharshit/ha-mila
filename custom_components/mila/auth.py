"""Mila API Authentication bound to Home Assistant OAuth."""
from __future__ import annotations

from asyncio import run_coroutine_threadsafe
from typing import Any, cast
from aiohttp import ClientSession

import milasdk
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_entry_oauth2_flow, aiohttp_client

from .const import DOMAIN

class MilaConfigEntryAuth(milasdk.auth.AbstractAsyncSession):  # type: ignore[misc]
    """Provide Mila API authentication tied to an OAuth2 based config entry."""
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        implementation: "MilaOauthImplementation",
    ) -> None:
        """Initialize Mila API Auth."""
        self.hass = hass
        self._implementation = implementation  # Store reference for cleanup
        self.session = config_entry_oauth2_flow.OAuth2Session(
            hass, config_entry, implementation
        )
        super().__init__(aiohttp_client.async_get_clientsession(self.hass))

    async def async_get_access_token(self) -> str:
        """Refresh and return new Mila API tokens using Home Assistant OAuth2 session."""
        await self.session.async_ensure_token_valid()
        return self.session.token["access_token"]  # type: ignore[no-any-return]

    async def async_close(self) -> None:
        """Close the underlying OAuth session."""
        await self._implementation.async_close()

class MilaOauthImplementation(config_entry_oauth2_flow.AbstractOAuth2Implementation):
    """Mila implementation of AbstractOAuth2Implementation."""
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry
    ) -> None:
        self.hass = hass
        self._username = config_entry.data["email"]
        self._password = config_entry.data["password"]
        # Get the shared session's connector to avoid creating orphaned sessions
        shared_session = aiohttp_client.async_get_clientsession(hass)
        self._auth = milasdk.MilaOauth2(
            token=cast(dict, config_entry.data["token"]),
            connector=shared_session.connector,
            connector_owner=False,  # HA owns the connector, don't close it
        )
        
    @property
    def name(self) -> str:
        return DOMAIN

    @property
    def domain(self) -> str:
        return DOMAIN

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        return ""

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        return {} #can accept the user/password here and use oauth flow if needed

    async def _async_refresh_token(self, token: dict) -> dict:
        try:
            # try to just refresh the token
            return await self._auth.async_refresh_token()
        except Exception as ex:
            try:
                # try the full auth request
                return await self._auth.async_request_token(self._username, self._password)
            except:
                # raise the original exception
                raise ex

    async def async_close(self) -> None:
        """Close the underlying MilaOauth2 session to prevent session leaks."""
        if self._auth is not None and not self._auth.closed:
            await self._auth.close()

