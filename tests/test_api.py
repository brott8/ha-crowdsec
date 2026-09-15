"""Tests for the CrowdSec LAPI client."""
from unittest.mock import Mock

from custom_components.crowdsec.api import CrowdSecApiClient, USER_AGENT


def test_client_uses_crowdsec_compatible_user_agent() -> None:
    """Avoid LAPI warnings caused by Home Assistant's multi-part default UA."""
    client = CrowdSecApiClient(
        scheme="http",
        host="lapi.local",
        port=8080,
        api_key="secret",
        unique_id="lapi.local:8080",
        session=Mock(),
    )

    assert client._headers["User-Agent"] == USER_AGENT
    assert USER_AGENT.split("/") == ["homeassistant-crowdsec", "1.0"]
