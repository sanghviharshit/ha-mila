"""Adds config flow for Mila integration."""

import asyncio
import logging
import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .milacloud import MilaAPI, MilaException
from .const import (
    CONF_DEVICES,
    CONF_SAVE_RESPONSES,
    CONF_TIMEOUT,
    CONF_USER_TOKEN,
    DATA_COORDINATOR,
    DEFAULT_SAVE_RESPONSES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    VALUES_SCAN_INTERVAL,
    VALUES_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

# TODO: Add oauth token expired handler
# TODO: Add config flow handler for options (save response, defaults overrides, etc)


class MilaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mila integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self.api = None
        self.user_input = {}

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            session = self.hass.helpers.aiohttp_client.async_get_clientsession()

            self.user_input[CONF_EMAIL] = user_input[CONF_EMAIL]
            self.user_input[CONF_PASSWORD] = user_input[CONF_PASSWORD]
            self.api = MilaAPI(
                self.user_input[CONF_EMAIL],
                self.user_input[CONF_PASSWORD],
                session=session,
            )

            try:
                self.user_input[CONF_USER_TOKEN] = await self.api.login()
                response = await self.api.get_devices()
                self.user_input[CONF_DEVICES] = [device["id"] for device in response]
                self.user_input[CONF_NAME] = self.user_input[CONF_EMAIL]
                await self.async_set_unique_id(
                    self.user_input[CONF_EMAIL].lower(), raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self.user_input[CONF_EMAIL],
                    data=self.user_input,
                )
            except MilaException as exception:
                _LOGGER.error(
                    f"Status: {exception.status}, Error Message: {exception.error_message}"
                )
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )
