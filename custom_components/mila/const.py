"""Module-wide constants for the Mila integration.

Anything that needs to be referenced from more than one place (and isn't
related to API queries or enums) lives here. Keep this file small and
import-cheap: it's pulled in by almost every other module.
"""
from __future__ import annotations

# Home Assistant integration "domain". Used as the key under `hass.data`,
# as the prefix on every unique_id, and as the manifest's `domain`.
DOMAIN = "mila"

# Shown on entities under the "Attribution" attribute so users can see
# where the data ultimately comes from.
ATTRIBUTION = "Data provided by Mila"

# Manufacturer string on the `DeviceInfo` we register with HA's device
# registry. Affects how the device card is labelled in the UI.
MANUFACTURER = "Milacares"

# ConfigEntry data keys. `email` / `password` use HA's own `CONF_EMAIL` /
# `CONF_PASSWORD` constants; the two below are integration-specific.
CONF_TOKEN = "token"        # Stored OAuth token bundle.
CONF_TIMEOUT = "timeout"    # Per-request timeout in seconds.

# Keys under which the coordinator stores per-entity-type sub-payloads
# inside `coordinator.data`. Centralising them avoids string typos
# diverging between writer (coordinator) and readers (device wrappers).
DATAKEY_ACCOUNT = "account"
DATAKEY_APPLIANCE = "appliance"
DATAKEY_LOCATION = "location"

# Allowed values for the two options-flow inputs. We expose dropdowns
# rather than free-text so users can't accidentally pick a 1-second poll
# interval and DOS Mila's API.
VALUES_SCAN_INTERVAL = [30, 60, 120, 300, 600]   # seconds
VALUES_TIMEOUT = [10, 15, 30, 45, 60]            # seconds

# Sensible defaults: a 2-minute poll and 30-second per-request timeout
# match what Mila's mobile app does and stay well clear of any
# rate-limit signals we've observed.
DEFAULT_SCAN_INTERVAL = VALUES_SCAN_INTERVAL[2]  # 120 seconds
DEFAULT_TIMEOUT = VALUES_TIMEOUT[2]              # 30 seconds
