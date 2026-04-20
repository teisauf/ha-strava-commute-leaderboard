"""Config flow for the Strava Commute Leaderboard integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    CONF_ATHLETE_NAME,
    CONF_CO2_PER_KM,
    CONF_COST_PER_KM,
    CONF_CURRENCY,
    CONF_STREAK_TOLERANCE,
    DEFAULT_CO2_PER_KM,
    DEFAULT_COST_PER_KM,
    DEFAULT_CURRENCY,
    DEFAULT_SCOPE,
    DEFAULT_STREAK_TOLERANCE,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

_LOGGER = logging.getLogger(__name__)


class StravaCommuteOAuthFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """OAuth2 config flow — one entry per athlete, each with their own Strava app."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._athlete_name: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        return {"scope": DEFAULT_SCOPE, "approval_prompt": "force"}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: ask for athlete name + this athlete's own Strava app credentials."""
        user_schema = vol.Schema(
            {
                vol.Required(CONF_ATHLETE_NAME): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
            },
        )

        if user_input is not None:
            self._athlete_name = user_input[CONF_ATHLETE_NAME].strip()
            self._client_id = user_input[CONF_CLIENT_ID].strip()
            self._client_secret = user_input[CONF_CLIENT_SECRET].strip()
            errors: dict[str, str] = {}
            if not self._athlete_name:
                errors[CONF_ATHLETE_NAME] = "empty_athlete_name"
            if not self._client_id:
                errors[CONF_CLIENT_ID] = "empty_client_id"
            if not self._client_secret:
                errors[CONF_CLIENT_SECRET] = "empty_client_secret"
            if errors:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self.add_suggested_values_to_schema(
                        user_schema, user_input
                    ),
                    errors=errors,
                )
            self.flow_impl = config_entry_oauth2_flow.LocalOAuth2Implementation(
                self.hass,
                DOMAIN,
                self._client_id,
                self._client_secret,
                OAUTH2_AUTHORIZE,
                OAUTH2_TOKEN,
            )
            return await self.async_step_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=user_schema,
        )

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Called by the OAuth helper once a refresh token is obtained."""
        athlete = data["token"].get("athlete") or {}
        athlete_id = athlete.get("id")
        if athlete_id is None:
            return self.async_abort(reason="missing_athlete_id")

        await self.async_set_unique_id(str(athlete_id))
        self._abort_if_unique_id_configured()

        name = self._athlete_name or athlete.get("firstname") or f"athlete_{athlete_id}"
        return self.async_create_entry(
            title=name,
            data={
                **data,
                CONF_ATHLETE_NAME: name,
                CONF_CLIENT_ID: self._client_id,
                CONF_CLIENT_SECRET: self._client_secret,
                "athlete_id": athlete_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StravaCommuteOptionsFlow(config_entry)


class StravaCommuteOptionsFlow(OptionsFlow):
    """Options flow for tuning per-athlete thresholds."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CO2_PER_KM,
                    default=options.get(CONF_CO2_PER_KM, DEFAULT_CO2_PER_KM),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_COST_PER_KM,
                    default=options.get(CONF_COST_PER_KM, DEFAULT_COST_PER_KM),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_CURRENCY,
                    default=options.get(CONF_CURRENCY, DEFAULT_CURRENCY),
                ): str,
                vol.Required(
                    CONF_STREAK_TOLERANCE,
                    default=options.get(
                        CONF_STREAK_TOLERANCE, DEFAULT_STREAK_TOLERANCE
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=14)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
