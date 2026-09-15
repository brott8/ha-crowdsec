"""Implementations of the geolocation providers, one per file.

Every module of this package is imported automatically, so adding a
provider is adding a single file here: no registry to edit, no import to
declare. The module declares its class with the @register decorator.
"""
from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

for _module in iter_modules(__path__):
    if not _module.name.startswith("_"):
        import_module(f"{__name__}.{_module.name}")
