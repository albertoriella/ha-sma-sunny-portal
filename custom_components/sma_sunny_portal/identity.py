"""Safe extraction of stable identity claims from validated SMA tokens."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping

from .const import OAUTH_ISSUER
from .errors import SmaSunnyPortalDataError

_TOKEN_DECODE_ERRORS = (ValueError, TypeError, UnicodeError, binascii.Error)


def account_id_from_access_token(access_token: str) -> str:
    """Return the SMA account subject without exposing malformed token data."""
    try:
        parts = access_token.split(".")
        if len(parts) != 3:
            raise ValueError
        encoded_payload = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload))
    except _TOKEN_DECODE_ERRORS:
        raise SmaSunnyPortalDataError(
            "SMA access token has no usable account identity"
        ) from None

    if not isinstance(payload, Mapping) or payload.get("iss") != OAUTH_ISSUER:
        raise SmaSunnyPortalDataError("SMA access token has an unexpected issuer")

    subject = payload.get("sub")
    if (
        not isinstance(subject, str)
        or not subject
        or any(character.isspace() for character in subject)
    ):
        raise SmaSunnyPortalDataError("SMA access token has no usable account identity")
    return subject
