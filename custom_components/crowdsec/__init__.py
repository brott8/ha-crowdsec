from __future__ import annotations

import importlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import your coordinator and API client
from .sensor import CrowdSecCoordinator
from .api import CrowdSecApiClient
from .geo import async_create_geo_provider

from .frontend import JSModuleRegistration

from .const import DOMAIN, CONF_SCHEME, CONF_GEO_PROVIDER, DEFAULT_GEO_PROVIDER

PLATFORMS = ["sensor"]


def entry_settings(entry: ConfigEntry) -> dict:
    """Values of the config entry, the options overriding the setup data."""
    return {**entry.data, **entry.options}

_LOGGER = logging.getLogger(__name__)


async def _async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and declare its resource.

    Before EVENT_HOMEASSISTANT_STARTED the Lovelace resource collection
    does not exist and a registration would be silently lost, so wait
    for the start - unless Home Assistant is already running (an
    installation made from the UI must show the card without a restart).
    """
    if hass.data[DOMAIN].get("frontend_registered"):
        return
    hass.data[DOMAIN]["frontend_registered"] = True

    async def _register(_event=None) -> None:
        await JSModuleRegistration(hass).async_register()

    if hass.state is CoreState.running:
        await _register()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CrowdSec from a config entry."""
    # Create the device in the registry FIRST.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="CrowdSec",
        model="LAPI",
        entry_type=dr.DeviceEntryType.SERVICE,
    )

    # Create the API client and coordinator.
    session = async_get_clientsession(hass)
    api_client = CrowdSecApiClient(
        host=entry.data["host"],
        port=entry.data["port"],
        api_key=entry.data["api_key"],
        scheme=entry.data[CONF_SCHEME],
        unique_id=entry.unique_id,
        session=session,
    )

    # Geolocation is opt-in: no provider, and no lookup at all, unless the
    # user picked one. The provider reads its own settings from the entry.
    settings = entry_settings(entry)
    geo_provider = await async_create_geo_provider(
        hass, settings.get(CONF_GEO_PROVIDER, DEFAULT_GEO_PROVIDER), settings
    )
    if geo_provider is not None:
        entry.async_on_unload(geo_provider.close)

    coordinator = CrowdSecCoordinator(hass, api_client, entry, geo_provider)

    # Store the coordinator in hass.data for platforms to access.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Reload the entry when the options are changed from the "Configure" dialog.
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # Make the bundled Lovelace card available (no manual resource needed).
    await _async_setup_frontend(hass)

    # Pre-load the device_trigger platform to avoid blocking import.
    await hass.async_add_executor_job(
        lambda: importlib.import_module(".device_trigger", package=__package__)
    )

    # Forward the setup to platforms (e.g., sensor).
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the Lovelace resource along with the last entry."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    await JSModuleRegistration(hass).async_unregister()


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    # This is called when the user saves the options form.
    # The easiest way to apply the changes is to reload the integration.
    await hass.config_entries.async_reload(entry.entry_id)
