"""Constants for generac."""
# Base component constants
NAME = "generac"
DOMAIN = "generac"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.0"

ATTRIBUTION = (
    "Data provided by https://app.mobilelinkgen.com/api. "
    "This is reversed engineered. Heavily inspired by "
    "https://github.com/digitaldan/openhab-addons/blob/generac-2.0/bundles/org.openhab.binding.generacmobilelink/README.md"
)
ISSUE_URL = "https://github.com/bentekkie/ha-generac/issues"

# Platforms
BINARY_SENSOR = "binary_sensor"
SENSOR = "sensor"
WEATHER = "weather"
IMAGE = "image"
PLATFORMS = [BINARY_SENSOR, SENSOR, WEATHER, IMAGE]


# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_COOKIES = "cookies"
CONF_AUTH_TOKEN = "auth_token"
CONF_AUTH_METHOD = "auth_method"

# Authentication methods
AUTH_METHOD_USERNAME_PASSWORD = "username_password"
AUTH_METHOD_COOKIES = "cookies"
AUTH_METHOD_TOKEN = "token"

# Defaults
DEFAULT_NAME = DOMAIN


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""


API_BASE = "https://app.mobilelinkgen.com/api"
LOGIN_BASE = "https://generacconnectivity.b2clogin.com/generacconnectivity.onmicrosoft.com/B2C_1A_MobileLink_SignIn"
