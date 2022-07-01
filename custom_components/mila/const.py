"""Constants used by the Mila integration."""
DOMAIN = "mila"

ATTRIBUTION = "Data provided by Mila"

MANUFACTURER = "Milacares"

CONF_TOKEN = "token"
CONF_TIMEOUT = "timeout"

DATAKEY_ACCOUNT = "account"
DATAKEY_APPLIANCE = "appliance"
DATAKEY_LOCATION = "location"

VALUES_SCAN_INTERVAL = [30, 60, 120, 300, 600]
VALUES_TIMEOUT = [10, 15, 30, 45, 60]

DEFAULT_SCAN_INTERVAL = VALUES_SCAN_INTERVAL[2]
DEFAULT_TIMEOUT = VALUES_TIMEOUT[2]
