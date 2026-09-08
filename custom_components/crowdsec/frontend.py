"""Serve and register the bundled Lovelace card.

The static path is always registered; the Lovelace resource is only
touched in storage mode (YAML dashboards declare their resources in
YAML). Registration must happen after Home Assistant has started: the
resource collection does not exist before that, and an attempt made
too early is silently lost.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN, FALLBACK_VERSION, JSMODULES, URL_BASE

try:  # Home Assistant 2024.11 and newer
    from homeassistant.components.lovelace.const import LOVELACE_DATA
except ImportError:  # pragma: no cover - older cores
    LOVELACE_DATA = "lovelace"

_LOGGER = logging.getLogger(__name__)


class JSModuleRegistration:
    """Serve the card files and reference the card in Lovelace."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._version = FALLBACK_VERSION

    @property
    def lovelace(self):
        """The Lovelace component, read when needed: it loads after us."""
        return self.hass.data.get(LOVELACE_DATA)

    async def _async_version(self) -> str:
        """The manifest version, used as the ?v= cache buster."""
        try:
            integration = await async_get_integration(self.hass, DOMAIN)
        except Exception:  # noqa: BLE001
            return FALLBACK_VERSION
        self._version = str(integration.version or FALLBACK_VERSION)
        return self._version

    @property
    def _mode(self) -> str:
        """Where Lovelace keeps its resources: 'storage' or 'yaml'."""
        return getattr(
            self.lovelace, "resource_mode", getattr(self.lovelace, "mode", "yaml")
        )

    async def async_register(self) -> None:
        """Serve the files, then declare the card resource."""
        if await self.async_register_path():
            await self.async_register_resource()

    async def async_register_resource(self) -> None:
        """Declare the card in the Lovelace resources (storage mode only).

        Needs the Lovelace resource collection, which only exists once
        Home Assistant has started.
        """
        version = await self._async_version()

        if self.lovelace is None:
            _LOGGER.warning(
                "Lovelace unavailable: add the resource manually -> "
                "url: %s/crowdsec-card.js?v=%s , type: module",
                URL_BASE,
                version,
            )
            return

        if self._mode != "storage":
            _LOGGER.info(
                "Lovelace in YAML mode: add the resource manually -> "
                "url: %s/crowdsec-card.js?v=%s , type: module",
                URL_BASE,
                version,
            )
            return

        await self._async_register_modules()

    async def async_register_path(self) -> bool:
        """Serve the files, one static path per module.

        Files, never the folder holding them: static paths are served
        outside Home Assistant authentication. Returns False when the
        files are missing, so the caller does not declare a resource that
        would only yield a 404.
        """
        www = Path(__file__).parent / "www"
        missing = await self.hass.async_add_executor_job(self._missing_files, www)
        if missing:
            _LOGGER.error(
                "Card files missing in %s: %s. The card cannot be served; "
                "reinstall the integration to restore them",
                www,
                ", ".join(missing),
            )
            return False
        try:
            await self.hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        f"{URL_BASE}/{module['filename']}",
                        str(www / module["filename"]),
                        True,
                    )
                    for module in JSMODULES
                ]
            )
        except (RuntimeError, ValueError) as err:
            # Already registered by a previous load of the entry.
            _LOGGER.debug("Static path already registered (%s): %s", URL_BASE, err)
            return True
        _LOGGER.info("Serving the CrowdSec card at %s", URL_BASE)
        return True

    @staticmethod
    def _missing_files(www: Path) -> list[str]:
        """Names of the card files absent from the www folder."""
        return [m["filename"] for m in JSMODULES if not (www / m["filename"]).is_file()]

    async def _async_load_resources(self) -> None:
        """Load the resource collection from storage if needed."""
        resources = self.lovelace.resources
        if getattr(resources, "loaded", True):
            return
        await resources.async_get_info()

    async def _async_register_modules(self) -> None:
        """Create the resource, or bring it to the current version."""
        await self._async_load_resources()

        existing = [
            resource
            for resource in self.lovelace.resources.async_items()
            if str(resource.get("url", "")).startswith(URL_BASE)
        ]

        for module in JSMODULES:
            if not module.get("resource"):
                continue  # loaded via relative import, static path is enough
            url = f"{URL_BASE}/{module['filename']}?v={self._version}"
            registered = False

            for resource in existing:
                if self._get_path(resource["url"]) != self._get_path(url):
                    continue
                registered = True
                if resource["url"] != url:
                    _LOGGER.info("Resource %s: updated to %s", resource["url"], url)
                    await self.lovelace.resources.async_update_item(
                        resource["id"], {"res_type": "module", "url": url}
                    )
                break

            if not registered:
                _LOGGER.info("Registering %s (%s)", module["name"], url)
                await self.lovelace.resources.async_create_item(
                    {"res_type": "module", "url": url}
                )

    async def async_unregister(self) -> None:
        """Remove the resource when the integration is removed."""
        if self.lovelace is None or self._mode != "storage":
            return
        await self._async_load_resources()
        for module in JSMODULES:
            if not module.get("resource"):
                continue
            url = f"{URL_BASE}/{module['filename']}"
            for resource in [
                item
                for item in self.lovelace.resources.async_items()
                if self._get_path(str(item.get("url", ""))) == url
            ]:
                await self.lovelace.resources.async_delete_item(resource["id"])

    @staticmethod
    def _get_path(url: str) -> str:
        """The url without its query parameters."""
        return url.split("?")[0]
