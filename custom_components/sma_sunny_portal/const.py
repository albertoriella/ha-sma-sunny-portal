"""Constants for SMA Sunny Portal Forecast."""

from datetime import timedelta
from typing import Final

API_BASE_URL: Final = "https://uiapi.sunnyportal.com/api/v1"
TOKEN_ENDPOINT: Final = (
    "https://login.sma.energy/auth/realms/SMA/protocol/openid-connect/token"
)
OAUTH_CLIENT_ID: Final = "SPpbeOS"
OAUTH_SCOPE: Final = "openid profile"
ACCESS_TOKEN_EXPIRY_MARGIN_SECONDS: Final = 30.0
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 30.0
DEFAULT_UPDATE_INTERVAL: Final = timedelta(minutes=15)

CONF_PLANT_ID: Final = "plant_id"
CONF_REFRESH_TOKEN: Final = "refresh_token"

DOMAIN: Final = "sma_sunny_portal"
NAME: Final = "SMA Sunny Portal Forecast"

TOKEN_STORAGE_VERSION: Final = 1
TOKEN_STORAGE_KEY_PREFIX: Final = f"{DOMAIN}.auth"
