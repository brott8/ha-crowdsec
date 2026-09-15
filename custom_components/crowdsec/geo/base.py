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
from collections import deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any, Deque, Dict, List, Optional, Tuple

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
    # Keep a slow remote provider from delaying the LAPI refresh. This covers
    # all batches in a single coordinator update, not each individual request.
    TOTAL_TIMEOUT = 8
    # Providers without a documented quota leave this disabled.
    MAX_REQUESTS_PER_WINDOW: Optional[int] = None
    REQUEST_WINDOW = 60
    RETRY_AFTER_FALLBACK = 60
    IP_FIELD = "ip"

    def __init__(self, hass: HomeAssistant, options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the provider with the shared HTTP session of Home Assistant."""
        super().__init__(hass, options)
        self._session = async_get_clientsession(hass)
        self._request_times: Deque[float] = deque()
        self._retry_after = 0.0

    @abstractmethod
    def _request(self, ips: List[str]) -> Tuple[str, str, Any]:
        """Return (method, url, json body or None) looking up these IPs."""

    @abstractmethod
    def _parse_entry(self, entry: Dict[str, Any]) -> GeoData:
        """Map one entry of the answer to the common geo attributes.

        Return an empty dict for an IP the service could not locate.
        """

    def _can_make_request(self) -> bool:
        """Return whether a request is allowed by the retry and rate limits."""
        now = monotonic()
        if now < self._retry_after:
            return False

        if self.MAX_REQUESTS_PER_WINDOW is None:
            return True

        window_start = now - self.REQUEST_WINDOW
        while self._request_times and self._request_times[0] <= window_start:
            self._request_times.popleft()

        return len(self._request_times) < self.MAX_REQUESTS_PER_WINDOW

    def _record_request(self) -> None:
        """Record a request for providers with a rolling request limit."""
        if self.MAX_REQUESTS_PER_WINDOW is not None:
            self._request_times.append(monotonic())

    def _set_retry_after(self, value: Optional[str]) -> None:
        """Set the next allowed request time from an HTTP Retry-After value."""
        delay = float(self.RETRY_AFTER_FALLBACK)
        if value:
            try:
                delay = max(0.0, float(value))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = max(
                        0.0,
                        (retry_at - datetime.now(timezone.utc)).total_seconds(),
                    )
                except (IndexError, TypeError, ValueError):
                    pass
        self._retry_after = max(self._retry_after, monotonic() + delay)

    async def async_lookup_ips(self, ips: List[str]) -> Optional[Dict[str, GeoData]]:
        """Resolve IPs within the provider's rate and total-time limits."""
        results: Dict[str, GeoData] = {}
        max_ips = self.BATCH_SIZE * self.MAX_BATCHES_PER_CALL

        try:
            async with asyncio.timeout(self.TOTAL_TIMEOUT):
                for start in range(0, min(len(ips), max_ips), self.BATCH_SIZE):
                    if not self._can_make_request():
                        _LOGGER.debug(
                            "%s geolocation lookup deferred by rate limiting", self.LABEL
                        )
                        break

                    chunk = ips[start : start + self.BATCH_SIZE]
                    method, url, body = self._request(chunk)
                    self._record_request()
                    try:
                        async with asyncio.timeout(self.TIMEOUT):
                            async with self._session.request(method, url, json=body) as resp:
                                if resp.status == 429:
                                    self._set_retry_after(resp.headers.get("Retry-After"))
                                    _LOGGER.warning(
                                        "%s rate limited; deferring lookups", self.LABEL
                                    )
                                    break
                                resp.raise_for_status()
                                data = await resp.json()
                    except (asyncio.TimeoutError, aiohttp.ClientError) as err:
                        _LOGGER.warning(
                            "%s geolocation lookup failed: %s", self.LABEL, err
                        )
                        break

                    for entry in data if isinstance(data, list) else [data]:
                        ip = entry.get(self.IP_FIELD) if isinstance(entry, dict) else None
                        if ip:
                            results[ip] = self._parse_entry(entry)
        except TimeoutError:
            _LOGGER.warning(
                "%s geolocation lookup exceeded its %s-second deadline",
                self.LABEL,
                self.TOTAL_TIMEOUT,
            )

        return results or None


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
