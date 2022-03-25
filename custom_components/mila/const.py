"""Constants used by the Mila integration."""
DOMAIN = "mila"

# Fan Services
SERVICE_SET_EXTRA_FEATURES = "fan_set_extra_features"

ATTRIBUTION = "Data provided by Mila"

CONF_NAME = "name"
CONF_DEVICES = "devices"
CONF_DEVICE = "device"
CONF_USER_TOKEN = "user_token"
DATA_COORDINATOR = "coordinator"

ERROR_TIME_FORMAT = "Time {} should be format 'HH:MM'"

MANUFACTURER = "Milacares"

MODEL_DEVICE = "Device"

UNDO_UPDATE_LISTENER = "undo_update_listener"

CONF_SAVE_RESPONSES = "save_responses"
CONF_TIMEOUT = "timeout"

VALUES_SCAN_INTERVAL = [30, 60, 120, 300, 600]
VALUES_TIMEOUT = [10, 15, 30, 45, 60]

DEFAULT_SAVE_LOCATION = "/config/custom_components/mila/milacloud/responses"
DEFAULT_SAVE_RESPONSES = True # TODO change it to False
DEFAULT_SCAN_INTERVAL = VALUES_SCAN_INTERVAL[2]
DEFAULT_TIMEOUT = VALUES_TIMEOUT[0]
