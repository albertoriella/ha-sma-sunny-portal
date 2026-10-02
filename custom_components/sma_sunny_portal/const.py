"""Constants for SMA Sunny Portal Forecast."""

from typing import Final

API_BASE_URL: Final = "https://uiapi.sunnyportal.com/api/v1"
TOKEN_ENDPOINT: Final = (
    "https://login.sma.energy/auth/realms/SMA/protocol/openid-connect/token"
)
OAUTH_CLIENT_ID: Final = "SPpbeOS"
OAUTH_SCOPE: Final = "openid profile"
ACCESS_TOKEN_EXPIRY_MARGIN_SECONDS: Final = 30.0
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 30.0
DOMAIN = "sma_sunny_portal"
NAME = "SMA Sunny Portal Forecast"
