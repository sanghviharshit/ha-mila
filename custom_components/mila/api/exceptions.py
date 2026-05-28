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
    """Raised when authentication fails or the token cannot be refreshed.

    Signals an unrecoverable auth state: the user must reauthenticate.
    Triggered for HTTP 400/401 token responses, missing `access_token` in
    the response body, and repeated 401s on data calls (which strongly
    suggest the refresh token itself is no longer valid).
    """
