"""Opt-in geolocation of the banned IPs.

Geolocation is disabled by default: no banned IP leaves Home Assistant
unless the user explicitly selects a provider, in the setup form or in
the "Configure" dialog of the integration.

The package separates the interface from the implementations:

    base.py             what a provider is (see GeoProvider)
    registry.py         the dropdown list and the factory
    providers/*.py      one file per implementation

Adding a provider is adding one file to providers/, holding a class
decorated with @register. Nothing else has to be edited: the modules of
that package are imported automatically, and the class carries its own
id, label and rank. Its label is translatable by adding the id under
selector.geo_provider.options in strings.json and the translations.
"""
from __future__ import annotations

from .base import GeoData, GeoProvider, RemoteJsonGeoProvider, as_number
from .registry import (
    PROVIDERS,
    async_create_geo_provider,
    provider_classes,
    provider_options,
    register,
)

# Importing the implementations registers them.
from . import providers  # noqa: F401  isort:skip

__all__ = [
    "PROVIDERS",
    "GeoData",
    "GeoProvider",
    "RemoteJsonGeoProvider",
    "as_number",
    "async_create_geo_provider",
    "provider_classes",
    "provider_options",
    "register",
]
