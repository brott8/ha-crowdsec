"""Shared fixtures of the CrowdSec integration tests."""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ from the repository root."""
    yield


@pytest.fixture(autouse=True)
def mock_frontend_dependencies(hass):
    """Pretend http, frontend and lovelace are set up.

    The card branch depends on them; the test core has no frontend
    package. The tests that need hass.http or Lovelace provide stand-ins.
    """
    hass.config.components.update({"http", "frontend", "lovelace"})
    yield


@pytest.fixture(autouse=True)
def mock_frontend(request):
    """Stub the bundled-card registration, which needs hass.http and Lovelace.

    Tests marked `real_frontend` exercise the registration itself and are
    left untouched. Branches without the card have nothing to stub.
    """
    import custom_components.crowdsec as integration

    if request.node.get_closest_marker("real_frontend") or not hasattr(
        integration, "JSModuleRegistration"
    ):
        yield
        return
    with patch.object(integration, "JSModuleRegistration") as registration:
        registration.return_value.async_register = AsyncMock()
        registration.return_value.async_register_path = AsyncMock(return_value=True)
        registration.return_value.async_register_resource = AsyncMock()
        registration.return_value.async_unregister = AsyncMock()
        yield
