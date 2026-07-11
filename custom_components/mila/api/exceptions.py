"""Exception types raised by the in-tree Mila API client.

The hierarchy is intentionally shallow: callers usually only need to
distinguish "the token is bad, ask the user to reauth" from "the API is
unhappy for some other reason, retry later." Specifically:

* `MilaError` is the base. Anything raised from this client is a subclass
  of it, so callers can blanket-catch with one line if they don't care
  about the distinction.
* `OAuthError` extends `MilaError` and signals that authentication is
  unrecoverable without user intervention. The integration translates
  this into Home Assistant's `ConfigEntryAuthFailed`, which prompts the
  user to re-enter credentials.

Any *transient* problem (HTTP 5xx, timeout, transport error) raises plain
`MilaError`. The data-update coordinator converts that to `UpdateFailed`
so Home Assistant will simply retry on the next poll cycle.
"""
from __future__ import annotations


class MilaError(Exception):
    """Base error for any failure talking to the Mila API.

    Used for transport-level problems (network errors, HTTP 5xx, malformed
    responses) and for GraphQL `errors` payloads that don't look like
    authentication failures.
    """


class OAuthError(MilaError):
    """Raised when the auth server actively rejects the grant.

    Signals an unrecoverable auth state: the user must reauthenticate.
    Triggered for HTTP 400/401/403 token responses (the server
    understood the request and refused it) and for repeated 401s on
    data calls (which strongly suggest the refresh token itself is no
    longer valid).

    Note the deliberate boundary: a malformed *success* response (200
    with no `access_token`), an HTTP 5xx, a timeout, or a transport
    error all raise plain `MilaError` instead, because they say nothing
    about whether the credentials are valid and should retry rather
    than prompt the user to reauthenticate. See `api/auth.py` for the
    classification.
    """
