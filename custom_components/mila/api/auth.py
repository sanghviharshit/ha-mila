"""OAuth2 password grant + refresh against Mila's Keycloak realm.

Mila's mobile app is a public OAuth2 client: there is no client secret,
and the Keycloak realm `prod` exposes the standard OIDC token endpoint
under `id.milacares.com`. We use the **resource-owner password
credentials grant** to exchange (username, password) for an access token
plus a refresh token, then exchange the refresh token for new access
tokens as they expire.

This module is intentionally a pair of stateless coroutines rather than
a class. State (the live token, expiry timestamps, etc.) belongs to the
caller. In this integration the caller is Home Assistant's
`config_entry_oauth2_flow.OAuth2Session`, which persists the token dict
to the config entry on disk.

Why not `async-oauthlib`?
  We previously pulled it in through `milasdk`. For a single grant type
  with a public client, the standard form-encoded POST in aiohttp is
  half a dozen lines and avoids the transitive dependency chain
  (`oauthlib`, `requests-oauthlib`, ...).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from aiohttp import ClientError, ClientSession

from .exceptions import OAuthError

_LOGGER = logging.getLogger(__name__)

# Public OIDC endpoint addresses for Mila's identity provider.
AUTH_BASE_URL = "https://id.milacares.com"
TOKEN_ENDPOINT = f"{AUTH_BASE_URL}/auth/realms/prod/protocol/openid-connect/token"

# Public client_id used by the Mila mobile app; safe to ship in the repo.
CLIENT_ID = "prod-ui"

# The realm rejects comma-separated scope lists, so we keep this
# space-separated and matching what the mobile app sends.
SCOPE = "email profile"

# We pretend the token expires this many seconds early to avoid sending a
# request with a token that's about to be rejected by the server clock.
# Keycloak's default access-token TTL is ~5 minutes, so 5 seconds is
# plenty of headroom without forcing extra refreshes.
_CLOCK_SKEW_SECONDS = 5


def _annotate_expiry(token: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp absolute expiry timestamps onto a freshly returned token dict.

    The OIDC response gives durations (`expires_in`, `refresh_expires_in`)
    in seconds. Storing absolute Unix timestamps lets later code compare
    against `time.time()` directly without having to remember when the
    token was issued. Home Assistant's `OAuth2Session` looks for these
    keys, so we add both whenever the server includes the matching
    `expires_in` / `refresh_expires_in` field.
    """
    now = int(time.time())
    if "expires_in" in token:
        token["expires_at"] = (
            now + int(float(token["expires_in"])) - _CLOCK_SKEW_SECONDS
        )
    if "refresh_expires_in" in token:
        # Not every grant flow returns this, but Keycloak's password grant
        # does, and refresh tokens themselves expire (`offline` scope is
        # the only thing that wouldn't).
        token["refresh_expires_at"] = (
            now + int(float(token["refresh_expires_in"])) - _CLOCK_SKEW_SECONDS
        )
    return token


async def request_token(
    session: ClientSession, username: str, password: str
) -> Dict[str, Any]:
    """Exchange (username, password) for a fresh OIDC token bundle.

    Used in two situations:

    1. During the initial config-flow setup, to verify the user typed
       the right credentials before saving the entry.
    2. As a fallback inside `MilaOauthImplementation._async_refresh_token`
       when the refresh token itself is no longer valid; rather than
       force the user to reauthenticate via the UI, we re-run the
       password grant with the credentials we already have stored.

    Args:
        session: aiohttp client session (shared with Home Assistant).
        username: account email.
        password: account password.

    Returns:
        The decoded token dict, annotated with absolute expiry stamps.

    Raises:
        OAuthError: the server rejected the credentials, the response
            body was missing `access_token`, or the transport failed.
    """
    # Standard "Resource Owner Password Credentials" payload per RFC 6749
    # section 4.3. We include `client_id` because Mila's Keycloak is
    # configured to require it even for public clients.
    data = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": username,
        "password": password,
        "scope": SCOPE,
    }
    try:
        async with session.post(TOKEN_ENDPOINT, data=data) as resp:
            # Keycloak returns JSON even on errors, with `error` and
            # `error_description` fields. `content_type=None` tells
            # aiohttp not to validate the response content-type header
            # (some 4xx responses come back without it).
            body = await resp.json(content_type=None)
            if resp.status != 200 or "access_token" not in body:
                # Surface the most helpful field available: usually
                # error_description ("Invalid user credentials"), falling
                # back to error code, then the raw body.
                raise OAuthError(
                    f"Token request failed (HTTP {resp.status}): "
                    f"{body.get('error_description') or body.get('error') or body}"
                )
            return _annotate_expiry(body)
    except ClientError as ex:
        # Network-level failure (DNS, TLS, connection reset). Treat as an
        # auth problem rather than a transient API error, because we
        # can't distinguish between "wrong credentials" and "auth server
        # unreachable" from this layer alone, and the user-visible
        # behaviour (please retry / reauth) is the same.
        raise OAuthError(f"Token request transport error: {ex}") from ex


async def refresh_token(session: ClientSession, refresh: str) -> Dict[str, Any]:
    """Exchange a refresh token for a new access + refresh token pair.

    Called by `MilaOauthImplementation._async_refresh_token` whenever
    Home Assistant decides the cached access token is about to expire.
    Keycloak rotates the refresh token on each call, so the caller must
    persist the entire returned dict, not just `access_token`.

    Args:
        session: aiohttp client session (shared with Home Assistant).
        refresh: the previously issued `refresh_token` value.

    Returns:
        The decoded token dict, annotated with absolute expiry stamps.

    Raises:
        OAuthError: the refresh token was rejected (revoked, expired,
            or otherwise invalid), the response was malformed, or the
            transport failed.
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh,
    }
    try:
        async with session.post(TOKEN_ENDPOINT, data=data) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200 or "access_token" not in body:
                raise OAuthError(
                    f"Token refresh failed (HTTP {resp.status}): "
                    f"{body.get('error_description') or body.get('error') or body}"
                )
            return _annotate_expiry(body)
    except ClientError as ex:
        raise OAuthError(f"Token refresh transport error: {ex}") from ex
