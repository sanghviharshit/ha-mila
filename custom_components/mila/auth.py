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

import asyncio
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .api import OAuthError, refresh_token, request_token
from .const import CONF_TOKEN, DOMAIN


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
        # Serializes `async_force_refresh_token`. Keycloak rotates the
        # refresh token on every grant, so two concurrent forced
        # refreshes would race: the second would present the
        # already-consumed refresh token and be rejected. The lock plus
        # the staleness check inside the method collapse a burst of
        # concurrent 401s into a single grant.
        self._force_refresh_lock = asyncio.Lock()

    async def async_get_access_token(self) -> str:
        """Return a valid access token, refreshing it transparently if needed.

        Called once per GraphQL request by `MilaClient`. The session
        handles caching: subsequent calls inside the token's validity
        window are a no-op.
        """
        await self.session.async_ensure_token_valid()
        return cast(str, self.session.token["access_token"])

    async def async_force_refresh_token(self) -> str:
        """Refresh the token now, regardless of its local expiry stamp.

        `async_ensure_token_valid` only refreshes when the locally
        stored `expires_at` says the token is stale. If Mila's server
        revokes a token early (password change, server-side session
        purge), the local copy still looks valid and every GraphQL
        request just gets a 401 back. `MilaClient` calls this after a
        401 so its retry runs with a genuinely fresh token, exercising
        the same refresh-then-password-grant fallback chain as a normal
        expiry. Without it the integration would escalate straight to a
        reauth prompt even though the stored credentials could have
        healed the session automatically.

        Mirrors what `OAuth2Session.async_ensure_token_valid` does after
        a refresh: persist the new bundle onto the config entry so it
        survives restarts.
        """
        # Snapshot before waiting on the lock: if another caller
        # refreshes while we queue, the token will have changed by the
        # time we get in, and we can reuse theirs instead of burning a
        # second grant against an already-rotated refresh token.
        seen_access_token = self.session.token.get("access_token")
        async with self._force_refresh_lock:
            current = self.session.token
            if current.get("access_token") != seen_access_token:
                return cast(str, current["access_token"])
            new_token = await self._implementation.async_refresh_token(
                dict(current)
            )
            self.hass.config_entries.async_update_entry(
                self.session.config_entry,
                data={**self.session.config_entry.data, CONF_TOKEN: new_token},
            )
            return cast(str, new_token["access_token"])

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
        # longer accepted). Be aware that Home Assistant persists
        # config-entry data as plain JSON under `.storage/` (readable
        # only by the HA user), so the password is NOT encrypted at
        # rest. Keeping it is a deliberate tradeoff: it lets the
        # integration heal itself with a fresh password grant instead
        # of interrupting the user with a reauth flow every time
        # Keycloak drops a refresh token.
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
        cheap path first (refresh-token grant); if that fails with a
        *rejection* we fall back to a full password-grant request using
        the credentials we stored at setup time. The fallback means a
        server-side refresh-token invalidation won't force the user
        through a reauth flow as long as the password still works.

        Transient failures (`MilaError`: network down, Keycloak 5xx)
        deliberately propagate without triggering the fallback: the
        password grant would fail on the same broken network anyway,
        and the coordinator translates `MilaError` into a retry rather
        than a reauth prompt.

        If *both* grants are rejected (typical when the user changed
        their password on milacares.com), we re-raise the original
        refresh error so the coordinator promotes it to
        `ConfigEntryAuthFailed` and HA prompts for new credentials.
        """
        try:
            # Happy path: hand the existing refresh token to Keycloak
            # and get a new pair back.
            return await refresh_token(self._session, token["refresh_token"])
        except (OAuthError, KeyError) as ex:
            # Either the refresh token was rejected (OAuthError) or the
            # stored token dict didn't have a `refresh_token` at all
            # (KeyError). Try the password-grant fallback.
            try:
                return await request_token(
                    self._session, self._username, self._password
                )
            except OAuthError as fallback_ex:
                # Both grants rejected. Surface the *original* error
                # when it carries the classification (OAuthError),
                # because "Token refresh rejected" usually tells the
                # user more than "Token request rejected" in logs. But
                # when the original was a KeyError (a token dict with
                # no refresh_token at all), re-raising it would let an
                # unclassified KeyError escape into callers that treat
                # unknown exceptions inconsistently; surface the
                # fallback's properly classified OAuthError instead.
                if isinstance(ex, OAuthError):
                    raise ex from None
                raise fallback_ex from ex

    async def async_close(self) -> None:
        """Release any owned resources.

        Currently a no-op: we share HA's aiohttp session so there's
        nothing to close. The method exists so `MilaConfigEntryAuth`
        can delegate to it uniformly.
        """
        return None
