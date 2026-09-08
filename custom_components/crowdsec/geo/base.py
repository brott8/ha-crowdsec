"""Interface of the geolocation providers.

A provider turns a list of banned IPs into geo attributes. Whatever the
provider, the attributes attached to a decision are the same, so the data
model exposed in the sensor attributes and in the event payloads never
depends on which provider is selected:

    country     ISO 3166-1 alpha-2 code (e.g. "FR")
    latitude    float
    longitude   float
    as_name     name of the autonomous system (e.g. "OVH SAS")
    as_number   AS number as an int (e.g. 16276)

This module holds only the interface. The implementations live one per
file in the providers subpackage.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Geo attributes attached to a decision (see the module docstring).
GeoData = Dict[str, Any]


class GeoProvider(ABC):
    """What every geolocation provider must offer."""

    # Value stored in the config entry; also the translation key of the
    # dropdown option. Must be unique.
    ID: str = ""
    # Dropdown label used when the translations carry no entry for ID.
    LABEL: str = ""
    # Rank in the dropdown, lowest first. Local providers come first, then
    # the ciphered remote ones, then the rest.
    PRIORITY: int = 100

    def __init__(self, hass: HomeAssistant, options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the provider with the values of the config entry.

        A provider reads its own settings from `options`, so adding one
        never requires touching the config flow.
        """
        self.hass = hass
        self.options = options or {}

    @abstractmethod
    async def async_lookup_ips(self, ips: List[str]) -> Optional[Dict[str, GeoData]]:
        """Resolve geo data for the given IPs.

        Returns a map of ip -> geo attributes. An IP the provider cannot
        locate maps to an empty dict, so the caller can cache the miss and
        stop retrying it. Returns None when the provider is unavailable
        (network failure, missing database, ...): the caller then leaves
        the decisions untouched and retries on the next poll.
        """

    def close(self) -> None:
        """Release the provider resources. Called from the event loop."""


class RemoteJsonGeoProvider(GeoProvider):
    """Ready-made base for the providers that query an HTTP(S) JSON service.

    A subclass only describes one request per batch of IPs (_request) and
    how to read one entry of the answer (_parse_entry). The answer is
    expected to be a list of entries (or a single entry), each carrying
    the looked-up IP in the IP_FIELD field.
    """

    BATCH_SIZE = 100
    # Stay well under the rate limits of the services; the remaining IPs
    # are picked up on the next polls.
    MAX_BATCHES_PER_CALL = 5
    TIMEOUT = 10
    IP_FIELD = "ip"

    def __init__(self, hass: HomeAssistant, options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the provider with the shared HTTP session of Home Assistant."""
        super().__init__(hass, options)
        self._session = async_get_clientsession(hass)

    @abstractmethod
    def _request(self, ips: List[str]) -> Tuple[str, str, Any]:
        """Return (method, url, json body or None) looking up these IPs."""

    @abstractmethod
    def _parse_entry(self, entry: Dict[str, Any]) -> GeoData:
        """Map one entry of the answer to the common geo attributes.

        Return an empty dict for an IP the service could not locate.
        """

    async def async_lookup_ips(self, ips: List[str]) -> Optional[Dict[str, GeoData]]:
        """Resolve the IPs batch by batch; see GeoProvider.async_lookup_ips."""
        results: Dict[str, GeoData] = {}
        max_ips = self.BATCH_SIZE * self.MAX_BATCHES_PER_CALL
        for start in range(0, min(len(ips), max_ips), self.BATCH_SIZE):
            chunk = ips[start : start + self.BATCH_SIZE]
            method, url, body = self._request(chunk)
            try:
                async with asyncio.timeout(self.TIMEOUT):
                    async with self._session.request(method, url, json=body) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                _LOGGER.warning("%s geolocation lookup failed: %s", self.LABEL, e)
                return results or None

            for entry in data if isinstance(data, list) else [data]:
                ip = entry.get(self.IP_FIELD) if isinstance(entry, dict) else None
                if ip:
                    results[ip] = self._parse_entry(entry)
        return results


def as_number(value: Any) -> Optional[int]:
    """Read an AS number out of 16276, "16276" or "AS16276 OVH SAS".

    Returns None when there is none: AS0 is the "unknown AS" placeholder
    of several services.
    """
    if isinstance(value, int):
        return value or None
    parts = str(value or "").strip().split()
    if not parts:
        return None
    text = parts[0]
    if text.upper().startswith("AS"):
        text = text[2:]
    try:
        return int(text) or None
    except ValueError:
        return None
