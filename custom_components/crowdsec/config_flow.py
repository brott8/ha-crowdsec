import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, DEFAULT_PORT, CONF_SCHEME, DEFAULT_SCAN_INTERVAL
from .api import CrowdSecApiClient

class CrowdSecConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Create a stable unique_id from the user's input.
            unique_id = f"{user_input["host"]}:{user_input["port"]}"
            
            # Set the unique_id for this flow to check for duplicates.
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # --- Start Validation ---
            session = async_get_clientsession(self.hass)
            api_client = CrowdSecApiClient(
                scheme=user_input[CONF_SCHEME],
                host=user_input["host"],
                port=user_input["port"],
                api_key=user_input["api_key"],
                unique_id=unique_id,
                session=session,
            )
            
            # Make a test API call
            test_data = await api_client.get_decisions()

            if test_data is not None: # `get_decisions` returns [] on success, None on failure
                # Connection successful, create the entry
                return self.async_create_entry(title=user_input["host"], data=user_input)
            else:
                # Set an error to display to the user
                errors["base"] = "cannot_connect"
            # --- End Validation ---

        # The schema is shown if there is no user_input or if there were errors
        schema = vol.Schema({
            vol.Required("host"): str,
            vol.Required("api_key"): str,
            vol.Optional("port", default=DEFAULT_PORT): int,
            vol.Optional(CONF_SCHEME, default="http"): vol.In(["http", "https"]),
            vol.Optional("scan_interval", default=DEFAULT_SCAN_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=10))
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors
        )