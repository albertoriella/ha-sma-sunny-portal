"""Exceptions raised by SMA Sunny Portal Forecast."""


class SmaSunnyPortalError(Exception):
    """Base exception for the integration."""


class SmaSunnyPortalAuthenticationError(SmaSunnyPortalError):
    """Raised when Sunny Portal rejects or cannot use authentication."""


class SmaSunnyPortalConnectionError(SmaSunnyPortalError):
    """Raised when Sunny Portal cannot be reached."""


class SmaSunnyPortalResponseError(SmaSunnyPortalError):
    """Raised when Sunny Portal returns an unsuccessful response."""


class SmaSunnyPortalRateLimitError(SmaSunnyPortalResponseError):
    """Raised when Sunny Portal rate-limits a request."""


class SmaSunnyPortalDataError(SmaSunnyPortalError):
    """Raised when a Sunny Portal payload violates the observed contract."""


class SmaSunnyPortalTokenPersistenceError(SmaSunnyPortalError):
    """Raised when a rotated refresh token cannot be persisted safely."""


class SmaSunnyPortalHistoryError(SmaSunnyPortalError):
    """Raised when private forecast history cannot be stored safely."""
