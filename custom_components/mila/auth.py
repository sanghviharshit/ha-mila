"""Mila authentication glue between Home Assistant and the `api` package.

Home Assistant's `config_entry_oauth2_flow.OAuth2Session` knows how to
persist a token dict to a config entry and how to ask an implementation
for a fresh one when the cached token is close to expiry. We give it a
custom implementation (`MilaOauthImplementation`) that performs the
OAuth2 password grant against Mila's Keycloak instance.

Two classes live here:

* `MilaConfigEntryAuth` is the thin coroutine-returning wrapper the
  GraphQL client (`MilaClient`) consumes via its `TokenProvider`. It
  just delegates to `OAuth2Session.async_ensure_token_valid`.

* `MilaOauthImplementation` plugs into HA's OAuth2 abstract base. The
  only method that does real work is `_async_refresh_token`; everything
  else either returns a placeholder (because the password grant doesn't
  need a redirect URL) or routes back through the in-tree API package.

We use the password grant rather than the auth-code-with-PKCE flow
because the latter would require either a redirect URL we control or an
in-browser flow inside HA, and Mila's Keycloak is configured to accept
the password grant from the `prod-ui` public client. The official mobile
app uses the same approach.
"""
from __future__ import annotations

from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .api import OAuthError, refresh_token, request_token
from .const import DOMAIN


class MilaConfigEntryAuth:
    """Token provider for `MilaClient`, backed by HA's `OAuth2Session`.

    One instance per config entry. The coordinator creates this in its
    constructor and hands `async_get_access_token` to `MilaClient` as a
    callable so the client doesn't need to know anything about HA.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        implementation: "MilaOauthImplementation",
    ) -> None:
        """Wire the OAuth2Session to the given implementation.

        Args:
            hass: Home Assistant core object.
            config_entry: the entry whose `data["token"]` we persist into.
            implementation: the password-grant implementation (also
                created by the coordinator). Held so we can close it on
                unload.
        """
        self.hass = hass
        self._implementation = implementation
        # `OAuth2Session` reads `config_entry.data["token"]` on init,
        # writes it back whenever a refresh succeeds, and handles the
        # "is this token still valid?" check for us. We use its
        # `async_ensure_token_valid` to drive refreshes.
        self.session = config_entry_oauth2_flow.OAuth2Session(
            hass, config_entry, implementation
        )

    async def async_get_access_token(self) -> str:
        """Return a valid access token, refreshing it transparently if needed.

        Called once per GraphQL request by `MilaClient`. The session
        handles caching: subsequent calls inside the token's validity
        window are a no-op.
        """
        await self.session.async_ensure_token_valid()
        return cast(str, self.session.token["access_token"])

    async def async_close(self) -> None:
        """Release any resources the implementation owns.

        Currently a passthrough because we share Home Assistant's
        aiohttp session and don't open anything new of our own.
        """
        await self._implementation.async_close()


class MilaOauthImplementation(
    config_entry_oauth2_flow.AbstractOAuth2Implementation
):
    """HA OAuth2 implementation that talks to Mila's Keycloak.

    HA's framework expects an implementation per OAuth provider; we
    register a domain-specific one rather than reusing HA's generic
    application credentials because Mila's flow is password-grant, not
    auth-code.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.hass = hass
        # Stored credentials. We need them for the fallback path inside
        # `_async_refresh_token` (when the refresh token itself is no
        # longer accepted). Storing the password isn't ideal but HA's
        # config-entry encryption protects it on disk.
        self._username = config_entry.data["email"]
        self._password = config_entry.data["password"]
        # Reuse HA's shared aiohttp session: connections are pooled
        # across the whole HA process, and we don't pay teardown cost
        # on unload.
        self._session = aiohttp_client.async_get_clientsession(hass)

    @property
    def name(self) -> str:
        """Human-readable name; HA uses it in some error messages."""
        return DOMAIN

    @property
    def domain(self) -> str:
        """Integration domain the implementation belongs to."""
        return DOMAIN

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Return the auth-code authorize URL (not used here).

        The abstract base requires us to implement this, but the
        password grant doesn't need it. Returning an empty string is
        safe: HA only calls this method when an auth-code flow is
        actually used.
        """
        return ""

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Convert auth-code external data to a token (not used).

        Same reasoning as `async_generate_authorize_url`: the password
        grant happens entirely server-to-server, so HA never invokes
        this method for us.
        """
        return {}

    async def _async_refresh_token(self, token: dict) -> dict:
        """Refresh a near-expiry token, falling back to password grant.

        Called by `OAuth2Session.async_ensure_token_valid`. We try the
        cheap path first (refresh-token grant); if that fails we fall
        back to a full password-grant request using the credentials we
        stored at setup time. The fallback means a temporary
        refresh-token expiry won't force the user through a reauth
        flow.

        If *both* fail (typical when the user changed their password
        on milacares.com), we re-raise the original refresh error so
        the coordinator promotes it to `ConfigEntryAuthFailed` and HA
        prompts for new credentials.
        """
        try:
            # Happy path: hand the existing refresh token to Keycloak
            # and get a new pair back.
            return await refresh_token(self._session, token["refresh_token"])
        except (OAuthError, KeyError) as ex:
            # Either the refresh-token call failed (OAuthError) or the
            # stored token dict didn't have a `refresh_token` at all
            # (KeyError). Try the password-grant fallback.
            try:
                return await request_token(
                    self._session, self._username, self._password
                )
            except OAuthError:
                # Both attempts failed. Surface the *original* error
                # because "Token refresh failed" usually tells the
                # user more than "Token request failed" in logs.
                raise ex from None

    async def async_close(self) -> None:
        """Release any owned resources.

        Currently a no-op: we share HA's aiohttp session so there's
        nothing to close. The method exists so `MilaConfigEntryAuth`
        can delegate to it uniformly.
        """
        return None
