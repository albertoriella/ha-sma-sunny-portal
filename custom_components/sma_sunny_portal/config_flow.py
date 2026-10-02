"""Config flow for SMA Sunny Portal Forecast."""

from __future__ import annotations

from typing import Any, override

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .bootstrap import BootstrapValidationResult, async_validate_credentials
from .const import CONF_PLANT_ID, CONF_REFRESH_TOKEN, DOMAIN, NAME
from .errors import (
    SmaSunnyPortalAuthenticationError,
    SmaSunnyPortalConnectionError,
    SmaSunnyPortalDataError,
    SmaSunnyPortalError,
    SmaSunnyPortalRateLimitError,
    SmaSunnyPortalResponseError,
    SmaSunnyPortalTokenPersistenceError,
)

USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_PLANT_ID): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="off")
        ),
        probatio.Required(CONF_REFRESH_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
        ),
    }
)

REAUTH_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_REFRESH_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
        )
    }
)


def _input_error(user_input: dict[str, Any]) -> tuple[str, str] | None:
    """Validate fields locally before any credential can be consumed."""
    plant_id = user_input.get(CONF_PLANT_ID)
    if not isinstance(plant_id, str) or not plant_id.isdecimal():
        return CONF_PLANT_ID, "invalid_plant_id"

    refresh_token = user_input.get(CONF_REFRESH_TOKEN)
    if (
        not isinstance(refresh_token, str)
        or not refresh_token
        or any(character.isspace() for character in refresh_token)
    ):
        return CONF_REFRESH_TOKEN, "invalid_refresh_token"
    return None


def _error_key(error: SmaSunnyPortalError) -> str:
    """Map safe client exceptions to translated flow errors."""
    if isinstance(error, SmaSunnyPortalAuthenticationError):
        return "invalid_auth"
    if isinstance(error, SmaSunnyPortalRateLimitError):
        return "rate_limited"
    if isinstance(
        error,
        (SmaSunnyPortalConnectionError, SmaSunnyPortalResponseError),
    ):
        return "cannot_connect"
    if isinstance(error, SmaSunnyPortalDataError):
        return "invalid_response"
    if isinstance(error, SmaSunnyPortalTokenPersistenceError):
        return "storage_error"
    return "unknown"


class SmaSunnyPortalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one SMA account and its initial plant."""

    VERSION = 1

    def _token_for_attempt(self, submitted_token: str) -> str:
        """Continue a rotated chain after a retry in the same flow."""
        if getattr(self, "_submitted_refresh_token", None) != submitted_token:
            self._submitted_refresh_token = submitted_token
            self._pending_refresh_token = None
        return getattr(self, "_pending_refresh_token", None) or submitted_token

    async def _async_remember_rotated_token(self, refresh_token: str) -> None:
        """Keep the newest token only in memory while the flow is active."""
        self._pending_refresh_token = refresh_token

    async def _async_validate(
        self,
        plant_id: str,
        submitted_token: str,
        *,
        persist_rotated_token: bool = False,
    ) -> BootstrapValidationResult:
        """Validate one attempt while preserving refresh-token rotation."""
        token_for_attempt = self._token_for_attempt(submitted_token)

        if persist_rotated_token:
            from .storage import SmaSunnyPortalRefreshTokenStore

            entry = self._get_reauth_entry()
            token_store = SmaSunnyPortalRefreshTokenStore(self.hass, entry.entry_id)

            async def async_observe(refresh_token: str) -> None:
                await self._async_remember_rotated_token(refresh_token)
                await token_store.async_save(refresh_token)

        else:
            async_observe = self._async_remember_rotated_token

        return await async_validate_credentials(
            async_get_clientsession(self.hass),
            plant_id,
            token_for_attempt,
            dt_util.now().date(),
            async_observe_rotated_token=async_observe,
        )

    @override
    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle initial manual bootstrap."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if field_error := _input_error(user_input):
                errors[field_error[0]] = field_error[1]
            else:
                plant_id = user_input[CONF_PLANT_ID]
                try:
                    result = await self._async_validate(
                        plant_id,
                        user_input[CONF_REFRESH_TOKEN],
                    )
                except SmaSunnyPortalError as err:
                    errors["base"] = _error_key(err)
                else:
                    await self.async_set_unique_id(result.account_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=NAME,
                        data={
                            CONF_PLANT_ID: plant_id,
                            CONF_REFRESH_TOKEN: result.refresh_token,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    @override
    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        """Begin reauthentication after a terminal token failure."""
        del entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Validate and atomically persist a replacement token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        plant_id = entry.data[CONF_PLANT_ID]

        if user_input is not None:
            validation_input = {
                CONF_PLANT_ID: plant_id,
                CONF_REFRESH_TOKEN: user_input.get(CONF_REFRESH_TOKEN),
            }
            if field_error := _input_error(validation_input):
                errors[field_error[0]] = field_error[1]
            else:
                try:
                    result = await self._async_validate(
                        plant_id,
                        user_input[CONF_REFRESH_TOKEN],
                        persist_rotated_token=True,
                    )
                except SmaSunnyPortalError as err:
                    errors["base"] = _error_key(err)
                else:
                    await self.async_set_unique_id(result.account_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={CONF_REFRESH_TOKEN: result.refresh_token},
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
        )
