"""Offline geolocation from a local MaxMind GeoLite2 database file."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant

from ..base import GeoData, GeoProvider, as_number
from ..registry import register

_LOGGER = logging.getLogger(__name__)


@register
class GeoLite2FileGeoProvider(GeoProvider):
    """Offline lookup in a local MaxMind GeoLite2 database.

    Nothing leaves Home Assistant: the IPs are resolved against .mmdb
    files on disk. The files are neither shipped nor downloaded by the
    integration; the user drops them, read-only, at one fixed place inside
    the Home Assistant configuration directory:

        crowdsec/GeoLite2-City.mmdb    country, latitude, longitude
        crowdsec/GeoLite2-ASN.mmdb     as_name, as_number (optional)

    These are the files CrowdSec itself downloads for its geoip-enrich
    parser, and the ones MaxMind offers with a free account. A file
    replaced on disk is reopened on the next poll.
    """

    ID = "geolite2_file"
    LABEL = "GeoLite2 file (local, offline, free)"
    PRIORITY = 10

    DIRECTORY = "crowdsec"
    LOCATION_FILENAME = "GeoLite2-City.mmdb"
    ASN_FILENAME = "GeoLite2-ASN.mmdb"

    def __init__(
        self, hass: HomeAssistant, options: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize the provider; the databases are opened on first use."""
        super().__init__(hass, options)
        self._location_reader: Any = None
        self._asn_reader: Any = None
        # Open databases, path -> (size, modification time), so a database
        # refreshed on disk is picked up without restarting Home Assistant.
        self._sources: Dict[str, Optional[tuple]] = {}
        self._loaded = False
        self._warned = False

    @property
    def location_path(self) -> str:
        """Where the City database is expected."""
        return self.hass.config.path(self.DIRECTORY, self.LOCATION_FILENAME)

    @property
    def asn_path(self) -> str:
        """Where the optional ASN database is expected."""
        return self.hass.config.path(self.DIRECTORY, self.ASN_FILENAME)

    async def async_lookup_ips(self, ips: List[str]) -> Optional[Dict[str, GeoData]]:
        """Resolve the IPs against the local databases, off the event loop."""
        return await self.hass.async_add_executor_job(self._lookup, ips)

    def close(self) -> None:
        """Close the open databases."""
        for reader in (self._location_reader, self._asn_reader):
            if reader is not None:
                reader.close()
        self._location_reader = self._asn_reader = None
        self._sources = {}
        self._loaded = False

    # --- executor side ---------------------------------------------------

    def _lookup(self, ips: List[str]) -> Optional[Dict[str, GeoData]]:
        """Read the databases. Runs in an executor thread."""
        if self._loaded and self._databases_changed():
            _LOGGER.debug("GeoLite2 database changed on disk, reopening")
            self.close()
        if not self._loaded:
            self._load()
        if self._location_reader is None and self._asn_reader is None:
            return None

        results: Dict[str, GeoData] = {}
        for ip in ips:
            geo: GeoData = {}
            try:
                if self._location_reader is not None:
                    geo.update(self._parse_location(self._location_reader.get(ip)))
                if self._asn_reader is not None:
                    geo.update(self._parse_asn(self._asn_reader.get(ip)))
            except ValueError:
                # Not an address this database can look up: cache as empty.
                geo = {}
            results[ip] = geo
        return results

    def _databases_changed(self) -> bool:
        """Whether a database was replaced, refreshed, added or removed."""
        return any(
            self._signature(path) != signature
            for path, signature in self._sources.items()
        )

    @staticmethod
    def _signature(path: str) -> Optional[tuple]:
        """Size and modification time of a database, None when absent."""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return (stat.st_size, stat.st_mtime)

    def _load(self) -> None:
        """Open the databases present at the fixed location."""
        self._loaded = True
        try:
            import maxminddb
        except ImportError:
            _LOGGER.error(
                "The maxminddb library is missing, the local GeoLite2 provider "
                "cannot be used"
            )
            return

        self._location_reader = self._open(maxminddb, self.location_path)
        self._asn_reader = self._open(maxminddb, self.asn_path)

        if self._location_reader is None and not self._warned:
            self._warned = True
            _LOGGER.error(
                "GeoLite2 database not found: put %s (and optionally %s) in place "
                "to geolocate the banned IPs locally",
                self.location_path,
                self.asn_path,
            )

    def _open(self, maxminddb: Any, path: str) -> Any:
        """Open one database, remembering its on-disk signature."""
        # Absent files are tracked too, so adding one later is noticed.
        self._sources[path] = self._signature(path)
        if self._sources[path] is None:
            return None
        try:
            reader = maxminddb.open_database(path)
        except (OSError, maxminddb.InvalidDatabaseError) as e:
            _LOGGER.error("Cannot open GeoLite2 database %s: %s", path, e)
            return None
        _LOGGER.debug("Using GeoLite2 database %s", path)
        return reader

    @staticmethod
    def _parse_location(record: Optional[Dict[str, Any]]) -> GeoData:
        """Map a City record to the common geo attributes."""
        if not record:
            return {}
        geo: GeoData = {}
        country = record.get("country") or record.get("registered_country") or {}
        if country.get("iso_code"):
            geo["country"] = country["iso_code"]
        location = record.get("location") or {}
        if location.get("latitude") is not None:
            geo["latitude"] = location["latitude"]
        if location.get("longitude") is not None:
            geo["longitude"] = location["longitude"]
        return geo

    @staticmethod
    def _parse_asn(record: Optional[Dict[str, Any]]) -> GeoData:
        """Map an ASN record to the common geo attributes."""
        if not record:
            return {}
        geo: GeoData = {}
        if record.get("autonomous_system_organization"):
            geo["as_name"] = record["autonomous_system_organization"]
        number = as_number(record.get("autonomous_system_number"))
        if number is not None:
            geo["as_number"] = number
        return geo
