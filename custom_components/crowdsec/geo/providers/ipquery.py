"""Geolocation through the ipquery.io service, over HTTPS."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..base import GeoData, RemoteJsonGeoProvider, as_number
from ..registry import register


@register
class IpQueryGeoProvider(RemoteJsonGeoProvider):
    """ipquery.io, free tier over HTTPS, no API key.

    The banned IPs are still sent to a third party, but over a ciphered
    connection. Bulk lookups take a comma-separated list of IPs; the batch
    is kept small to keep the URL short.
    """

    ID = "ipquery"
    LABEL = "ipquery.io (remote, HTTPS, free)"
    PRIORITY = 20

    BASE_URL = "https://api.ipquery.io/"
    BATCH_SIZE = 50

    def _request(self, ips: List[str]) -> Tuple[str, str, Any]:
        return "GET", f"{self.BASE_URL}{','.join(ips)}?format=json", None

    def _parse_entry(self, entry: Dict[str, Any]) -> GeoData:
        location = entry.get("location") or {}
        # Unlocatable addresses come back with an empty country and
        # meaningless coordinates near latitude 0, longitude 0.
        if not location.get("country_code"):
            return {}

        geo: GeoData = {"country": location["country_code"]}
        if location.get("latitude") is not None:
            geo["latitude"] = location["latitude"]
        if location.get("longitude") is not None:
            geo["longitude"] = location["longitude"]

        isp = entry.get("isp") or {}
        if isp.get("org") or isp.get("isp"):
            geo["as_name"] = isp.get("org") or isp["isp"]
        number = as_number(isp.get("asn"))
        if number is not None:
            geo["as_number"] = number
        return geo
