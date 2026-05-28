"""Config and options flows for the Mila integration.

Home Assistant calls into the classes in this file when the user adds a
new integration entry, re-authenticates an existing one, or opens the
*Configure* dialog. The flow logic is intentionally light: the bulk of
the work (talking to Mila's auth server) happens in the in-tree `api`
package.

User-facing flows:

1. **Initial setup (`async_step_user`)** — show the credentials form,
   call `request_token` to verify them, store the resulting token bundle
   in the config entry so the coordinator can use it immediately.

2. **Reauthentication (`async_step_reauth` + `_confirm`)** — triggered
   when the coordinator raises `ConfigEntryAuthFailed`. Same form, but
   the email field is pre-filled and unchanged on save (only the
   password is updated).

3. **Options (`MilaOptionsFlowHandler`)** — opened from the integration
   card. Lets the user pick scan interval and per-request timeout. The
   listener registered in `async_setup_entry` pushes these onto the
   running coordinator without a reload.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import (
    CONN_CLASS_CLOUD_POLL,
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import MilaError, OAuthError, request_token
from .const import (
    CONF_TIMEOUT,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    VALUES_SCAN_INTERVAL,
    VALUES_TIMEOUT,
)

# Schema for the initial setup step. Both fields are required; HA renders
# a username text field and a masked password field automatically.
CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

# Schema for the options dialog. `vol.In` restricts inputs to the
# enumerated lists so users can't accidentally type a 1-second interval.
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.In(
            VALUES_SCAN_INTERVAL
        ),
        vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.In(VALUES_TIMEOUT),
    }
)


class MilaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial-setup + reauthentication flow.

    Subclasses `ConfigFlow` so HA registers it under the `mila` domain.
    `VERSION = 1` lets us add a `async_migrate_entry` in the future if we
    ever need to change the persisted data shape.
    """

    VERSION = 1
    DOMAIN = DOMAIN
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        # Holds whatever the user has entered so far across reauth steps.
        self._existing_entry: dict | None = None
        self._user_input: dict = {}
        # Used to feed placeholders (like the email being reauthed) into
        # the form's description string in `translations/en.json`.
        self._description_placeholders: dict | None = None
        super().__init__()

    @property
    def logger(self) -> logging.Logger:
        """Module logger; tagged with the flow's module name."""
        return logging.getLogger(__name__)

    def _get_schema(self, step_id: str) -> vol.Schema:
        """Return the right form schema for the current step.

        The reauth step only asks for the password (the email is fixed
        to whatever the entry already stored).
        """
        if step_id == "user":
            return CREDENTIALS_SCHEMA
        return vol.Schema({vol.Required(CONF_PASSWORD): str})

    async def _test_connection_and_set_token(self) -> None:
        """Exchange the entered credentials for a real OAuth token bundle.

        If `request_token` succeeds we know:
          * the credentials are valid;
          * Mila's auth server is reachable from this HA instance.

        We stash the returned token bundle into `_user_input` so it
        ends up in `config_entry.data["token"]` once we call
        `async_create_entry`. The coordinator picks it up from there
        on first refresh.
        """
        session = aiohttp_client.async_get_clientsession(self.hass)
        token = await request_token(
            session,
            self._user_input[CONF_EMAIL],
            self._user_input[CONF_PASSWORD],
        )
        self.logger.info("Successfully authenticated")
        self._user_input[CONF_TOKEN] = token

    def _show_setup_form(
        self,
        user_input: dict | None = None,
        errors: dict | None = None,
        step_id: str = "user",
    ) -> FlowResult:
        """Render the form for the named step, optionally with errors.

        Errors are keyed by field name; an empty key (`"base"`) is shown
        above the form rather than next to a specific field.
        """
        if user_input is None:
            user_input = {}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._get_schema(step_id),
            errors=errors or {},
            description_placeholders=self._description_placeholders,
        )

    async def _validate_and_create_entry(
        self, user_input: dict, step_id: str
    ) -> FlowResult:
        """Common path for both initial setup and reauth.

        Stitches together the password the user just typed with the
        rest of the entry data (email, etc.) and then calls
        `_test_connection_and_set_token`. On success it either creates
        a new entry (`step_id == "user"`) or updates the existing one
        and triggers a reload (reauth).
        """
        self._user_input[CONF_PASSWORD] = user_input[CONF_PASSWORD]

        # If we're in reauth, the user wasn't asked for an email; pick
        # it up from the existing entry. For initial setup, the email
        # is in `user_input` because the schema requires it.
        extra_inputs = self._existing_entry if self._existing_entry else user_input
        self._user_input[CONF_EMAIL] = extra_inputs[CONF_EMAIL]

        # Use the email as a unique identifier so the user can't
        # configure the same account twice.
        if self.unique_id is None:
            await self.async_set_unique_id(self._user_input[CONF_EMAIL])
            self._abort_if_unique_id_configured()

        try:
            await self._test_connection_and_set_token()
        except OAuthError as ex:
            # Bad credentials. The matching error string is in
            # `translations/en.json` under `config.error.invalid_auth`.
            self.logger.warning("Mila authentication rejected: %s", ex)
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._get_schema(step_id),
                errors={"base": "invalid_auth"},
            )
        except MilaError as ex:
            # Network / server / unexpected response. Tell the user to
            # try again later rather than blaming their credentials.
            self.logger.warning("Mila API not reachable during setup: %s", ex)
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._get_schema(step_id),
                errors={"base": "cannot_connect"},
            )
        except Exception as ex:  # pragma: no cover - defensive catch
            # Anything we didn't anticipate. We still want the user to
            # see the form again rather than an internal-error dialog,
            # so we surface a generic "unknown" error string.
            self.logger.exception("Unexpected error during Mila setup: %s", ex)
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._get_schema(step_id),
                errors={"base": "unknown"},
            )

        if step_id == "user":
            # Brand-new entry. The title shows up in the integration
            # list and as the device-card name.
            return self.async_create_entry(
                title=self._user_input[CONF_EMAIL],
                data=self._user_input,
            )

        # Reauth path: update the existing entry's data with the new
        # password / token and force a reload so the running coordinator
        # picks them up immediately.
        entry = await self.async_set_unique_id(self.unique_id)
        self.hass.config_entries.async_update_entry(entry, data=self._user_input)
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Initial-setup entry point. Called when the user adds the integration."""
        if user_input is None:
            return self._show_setup_form(user_input, {})
        return await self._validate_and_create_entry(user_input, "user")

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Triggered by `ConfigEntryAuthFailed` from the coordinator."""
        await self.async_set_unique_id(entry_data[CONF_EMAIL])
        # Remember the existing entry so the confirm step can keep the
        # email unchanged.
        self._existing_entry = {**entry_data}
        self._description_placeholders = {CONF_EMAIL: entry_data[CONF_EMAIL]}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[dict[str, str]] = None
    ) -> FlowResult:
        """Reauth confirm step: ask for the new password and re-validate."""
        if user_input is None:
            return self._show_setup_form(step_id="reauth_confirm")
        return await self._validate_and_create_entry(user_input, "reauth_confirm")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Tell HA which class handles the *Configure* dialog."""
        return MilaOptionsFlowHandler(config_entry)


class MilaOptionsFlowHandler(OptionsFlow):
    """Options dialog: scan interval + per-request timeout.

    `__init__.async_update_options` listens for saves on this flow and
    applies them to the live coordinator without a reload.
    """

    def __init__(self, entry: ConfigEntry) -> None:
        # Stored for symmetry / future use; we don't currently need it
        # because saved options come back to us via the callback.
        self.entry = entry

    async def async_step_init(
        self, user_input: Optional[dict[str, str]] = None
    ) -> FlowResult:
        """Show the options form, or save the submitted values."""
        if user_input is not None:
            # `async_create_entry` here writes to `entry.options`, not
            # `entry.data`. HA fires the update listener afterwards.
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)
