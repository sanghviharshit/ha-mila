"""Adds config flow for Mila integration."""

from asyncio.log import logger
import logging
from typing import Any, Mapping, Optional
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow, CONN_CLASS_CLOUD_POLL
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from milasdk import DefaultAsyncSession
from milasdk.api import MilaApi
from .const import (
    CONF_TIMEOUT,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    VALUES_SCAN_INTERVAL,
    VALUES_TIMEOUT,
)

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.In(VALUES_SCAN_INTERVAL),
        vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.In(VALUES_TIMEOUT)
    }
)

class MilaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mila integration."""

    VERSION = 1
    DOMAIN = DOMAIN
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self):
        self.user_input = {}
        self._entry_data_for_reauth: Mapping[str, Any] = {}
        super().__init__()

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)   

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self.user_input[CONF_EMAIL] = user_input[CONF_EMAIL]
            self.user_input[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            try:
                #test the connection and set the token
                await self.test_connection_and_set_token()
                    
                #get the existing entry
                existing_entry = await self.async_set_unique_id(self.user_input[CONF_EMAIL])

                #if we have an entry, assume that we want to update it (treat as re-auth)
                if existing_entry:
                    self.hass.config_entries.async_update_entry(existing_entry, data=user_input)
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(existing_entry.entry_id)
                    )
                    return self.async_abort(reason="reauth_successful")

                #if we didn't have an entry, create one
                return self.async_create_entry(
                    title=self.user_input[CONF_EMAIL],
                    data=self.user_input
                )            
            #TODO: more exception handling (needs sdk fixes)
            except Exception as ex:
                logger.exception(ex)
                errors["base"] = "invalid_auth"     

        return self.async_show_form(
            step_id="user",
            data_schema=CREDENTIALS_SCHEMA,
            errors=errors
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle configuration by re-auth."""
        self._entry_data_for_reauth = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[dict[str, str]] = None
    ) -> FlowResult:
        """Handle re-auth completion."""
        if not user_input:
            return self.async_show_form(
                step_id="reauth_confirm", 
                data_schema=CREDENTIALS_SCHEMA
            )

        conf = {
            **self._entry_data_for_reauth, 
            CONF_EMAIL: user_input[CONF_EMAIL],
            CONF_PASSWORD: user_input[CONF_PASSWORD]
        }

        return await self.async_step_user(conf)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Define the config flow to handle options."""
        return MilaOptionsFlowHandler(config_entry)        

    async def test_connection_and_set_token(self):
        session = aiohttp_client.async_get_clientsession(self.hass)
        # create the api client
        auth_session = DefaultAsyncSession(
            session, 
            self.user_input[CONF_EMAIL],
            self.user_input[CONF_PASSWORD]
        )        
        api = MilaApi(auth_session)

        #try to get account information, if we do, we're good
        await api.get_account()
        self.logger.info("Successfully authenticated")

        #set the token to the one just obtained
        self.user_input[CONF_TOKEN] = auth_session.token
   
class MilaOptionsFlowHandler(OptionsFlow):
    """Handle an Mila options flow."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry

    async def async_step_init(
        self, user_input: Optional[dict[str, str]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=OPTIONS_SCHEMA
        )