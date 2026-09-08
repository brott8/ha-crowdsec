"""Registry of the geolocation providers.

Holds the list shown in the dropdown and turns the selected id into a
provider instance. Implementations register themselves with @register,
so nothing here has to be edited when one is added.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant

from ..const import GEO_PROVIDER_NONE
from .base import GeoProvider

_LOGGER = logging.getLogger(__name__)

# Provider id -> class, filled by @register. GEO_PROVIDER_NONE is not a
# provider: it is the "disabled" choice of the dropdown.
PROVIDERS: Dict[str, type[GeoProvider]] = {}


def register(cls: type[GeoProvider]) -> type[GeoProvider]:
    """Class decorator adding a provider to the dropdown and the factory."""
    if not cls.ID or cls.ID == GEO_PROVIDER_NONE or cls.ID in PROVIDERS:
        raise ValueError(f"Invalid or duplicate geolocation provider id {cls.ID!r}")
    PROVIDERS[cls.ID] = cls
    return cls


def provider_classes() -> List[type[GeoProvider]]:
    """The registered providers, in dropdown order."""
    return sorted(PROVIDERS.values(), key=lambda cls: (cls.PRIORITY, cls.ID))


def provider_options() -> List[Dict[str, str]]:
    """Choices of the geolocation dropdown: disabled first, then the providers."""
    return [
        {"value": GEO_PROVIDER_NONE, "label": "Disabled"},
        *({"value": cls.ID, "label": cls.LABEL} for cls in provider_classes()),
    ]


async def async_create_geo_provider(
    hass: HomeAssistant, provider_id: str, options: Optional[Dict[str, Any]] = None
) -> Optional[GeoProvider]:
    """Instantiate the configured provider, or None when geolocation is disabled."""
    if provider_id == GEO_PROVIDER_NONE:
        return None
    provider_cls = PROVIDERS.get(provider_id)
    if provider_cls is None:
        _LOGGER.error(
            "Unknown geolocation provider %r, geolocation is disabled", provider_id
        )
        return None
    return provider_cls(hass, options)
