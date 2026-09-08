"""Geolocation through the ip-api.com service."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..base import GeoData, RemoteJsonGeoProvider, as_number
from ..registry import register


@register
class IpApiGeoProvider(RemoteJsonGeoProvider):
    """ip-api.com, free tier: plain HTTP only, non-commercial use.

    The free endpoint refuses HTTPS, so the banned IPs travel in clear
    text. Batches of up to 100 IPs per request, 15 requests per minute.
    """

    ID = "ip_api"
    LABEL = "ip-api.com (remote, HTTP, free)"
    PRIORITY = 30

    BATCH_URL = (
        "http://ip-api.com/batch?fields=status,countryCode,lat,lon,as,asname,query"
    )
    IP_FIELD = "query"

    def _request(self, ips: List[str]) -> Tuple[str, str, Any]:
        return "POST", self.BATCH_URL, ips

    def _parse_entry(self, entry: Dict[str, Any]) -> GeoData:
        if entry.get("status") != "success":
            # Not locatable (private/reserved range, ...): cache as empty.
            return {}
        geo: GeoData = {}
        if entry.get("countryCode"):
            geo["country"] = entry["countryCode"]
        if entry.get("lat") is not None:
            geo["latitude"] = entry["lat"]
        if entry.get("lon") is not None:
            geo["longitude"] = entry["lon"]
        if entry.get("asname"):
            geo["as_name"] = entry["asname"]
        # The "as" field looks like "AS16276 OVH SAS".
        number = as_number(entry.get("as"))
        if number is not None:
            geo["as_number"] = number
        return geo
