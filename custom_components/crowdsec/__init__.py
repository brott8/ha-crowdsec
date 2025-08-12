from __future__ import annotations

import importlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import your coordinator and API client
from .sensor import CrowdSecCoordinator
from .api import CrowdSecApiClient 

from .const import DOMAIN

PLATFORMS = ["sensor"]

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
    api_client = CrowdSecApiClient(**entry.data, unique_id=entry.unique_id, session=session)
    coordinator = CrowdSecCoordinator(hass, api_client, entry)

    # Store the coordinator in hass.data for platforms to access.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

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


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    # This is called when the user saves the options form.
    # The easiest way to apply the changes is to reload the integration.
    await hass.config_entries.async_reload(entry.entry_id)