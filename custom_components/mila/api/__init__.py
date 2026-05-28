"""Self-contained Mila API client.

This package is the only thing in the integration that knows how to talk
to `graph-api.milacares.com`. Everything else (config flow, coordinator,
device wrappers, entities) imports from here.

The public surface is deliberately small. We re-export:

* Token helpers (`request_token`, `refresh_token`) — used by `auth.py`
  to drive Home Assistant's `OAuth2Session`.
* The low-level GraphQL client (`MilaClient`) and the high-level facade
  (`MilaApi`).
* Every Mila enum the integration touches.
* The exception hierarchy (`MilaError`, `OAuthError`).

Internal modules:

* `client.py` — `MilaClient` + `MilaApi`.
* `auth.py` — OAuth2 token + refresh against Keycloak.
* `queries.py` — every GraphQL document string we send.
* `enums.py` — all server-side enums mirrored in Python.
* `exceptions.py` — `MilaError`, `OAuthError`.

Imports inside the package use relative paths so callers can swap the
package out (vendor it elsewhere, rename it) without sprinkling absolute
imports.
"""
from __future__ import annotations

from .auth import refresh_token, request_token
from .client import MilaApi, MilaClient
from .enums import (
    ApplianceMode,
    ApplianceSensorKind,
    FanMode,
    FanSpeed,
    PerformanceMode,
    PerformanceProfile,
    SmartModeKind,
    SoundsConfig,
)
from .exceptions import MilaError, OAuthError

__all__ = [
    # Enums
    "ApplianceMode",
    "ApplianceSensorKind",
    "FanMode",
    "FanSpeed",
    "PerformanceMode",
    "PerformanceProfile",
    "SmartModeKind",
    "SoundsConfig",
    # Client + facade
    "MilaApi",
    "MilaClient",
    # Auth coroutines
    "refresh_token",
    "request_token",
    # Exceptions
    "MilaError",
    "OAuthError",
]
