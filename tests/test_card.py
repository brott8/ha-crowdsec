"""Tests of the bundled Lovelace card registration."""
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crowdsec.const import DOMAIN, URL_BASE
from custom_components.crowdsec.frontend import JSModuleRegistration

try:
    from homeassistant.components.lovelace.const import LOVELACE_DATA
except ImportError:  # older cores
    LOVELACE_DATA = "lovelace"

pytestmark = pytest.mark.real_frontend

ENTRY_DATA = {
    "host": "lapi.local",
    "port": 8080,
    "api_key": "secret",
    "scheme": "http",
    "scan_interval": 60,
}


@pytest.fixture
def http(hass):
    """A stand-in for the http component."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    return hass.http


@pytest.fixture
def lovelace(hass):
    """A stand-in for Lovelace in storage mode with no resource yet."""
    lovelace = MagicMock()
    lovelace.resource_mode = "storage"
    lovelace.resources.loaded = True
    lovelace.resources.async_items = MagicMock(return_value=[])
    lovelace.resources.async_create_item = AsyncMock()
    lovelace.resources.async_update_item = AsyncMock()
    hass.data[LOVELACE_DATA] = lovelace
    return lovelace


def _patch_decisions():
    return patch(
        "custom_components.crowdsec.api.CrowdSecApiClient.get_decisions",
        AsyncMock(return_value=[]),
    )


async def _setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="lapi.local:8080", title="lapi.local")
    entry.add_to_hass(hass)
    with _patch_decisions():
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _started(hass):
    """Make sure the startup listener ran."""
    if hass.state is not CoreState.running:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()


async def test_card_files_are_served_as_soon_as_the_entry_loads(hass, http, lovelace):
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    # Registered at setup, before any startup event.
    http.async_register_static_paths.assert_awaited_once()
    configs = http.async_register_static_paths.await_args.args[0]
    assert {c.url_path for c in configs} == {
        f"{URL_BASE}/crowdsec-card.js",
        f"{URL_BASE}/world-map.js",
    }
    # ... and the files they point at really exist.
    for config in configs:
        assert os.path.isfile(config.path), config.path


async def test_resource_is_declared_once_started(hass, http, lovelace):
    await _setup(hass)
    await _started(hass)

    lovelace.resources.async_create_item.assert_awaited_once()
    resource = lovelace.resources.async_create_item.await_args.args[0]
    assert resource["res_type"] == "module"
    assert resource["url"].startswith(f"{URL_BASE}/crowdsec-card.js?v=")
    # Only the card is declared; the map is imported by the card itself.
    assert lovelace.resources.async_create_item.await_count == 1


async def test_missing_card_files_are_reported_not_served(hass, http, lovelace, caplog):
    with patch.object(JSModuleRegistration, "_missing_files", return_value=["crowdsec-card.js"]):
        entry = await _setup(hass)
        await _started(hass)

    assert entry.state is ConfigEntryState.LOADED
    http.async_register_static_paths.assert_not_awaited()
    lovelace.resources.async_create_item.assert_not_awaited()
    assert "Card files missing" in caplog.text
    assert "crowdsec-card.js" in caplog.text


async def test_failed_resource_declaration_is_logged_and_retried(hass, http, lovelace, caplog):
    lovelace.resources.async_items = MagicMock(side_effect=RuntimeError("boom"))
    caplog.set_level(logging.ERROR)

    entry = await _setup(hass)
    await _started(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert "Declaring the CrowdSec card resource failed" in caplog.text
    # The flag is cleared so a reload of the integration tries again.
    assert hass.data[DOMAIN]["frontend_registered"] is False


async def test_static_path_registered_again_on_reload(hass, http, lovelace):
    entry = await _setup(hass)
    await _started(hass)
    http.async_register_static_paths.reset_mock()
    # A second registration of the same path is refused by aiohttp.
    http.async_register_static_paths.side_effect = RuntimeError("already registered")

    with _patch_decisions():
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    http.async_register_static_paths.assert_awaited_once()
    # The resource was declared once; no duplicate on reload.
    assert lovelace.resources.async_create_item.await_count == 1
