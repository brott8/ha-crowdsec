# geo.py
"""Optional IP geolocation via the external ip-api.com service.

Used as a credential-less alternative to reading the LAPI alerts
(which requires machine auth). Banned IPs are sent to ip-api.com,
so this is strictly opt-in.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

# Free endpoint (HTTP only). Batches of up to 100 IPs per request,
# rate-limited to 15 requests per minute.
BATCH_URL = "http://ip-api.com/batch?fields=status,countryCode,lat,lon,as,asname,query"
BATCH_SIZE = 100
# Stay well under the rate limit; remaining IPs are picked up on later polls.
MAX_BATCHES_PER_CALL = 5


async def async_lookup_ips(
    session: aiohttp.ClientSession, ips: List[str]
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Resolve geo data for the given IPs.

    Returns a map of ip -> geo attributes (empty dict for IPs the service
    cannot locate, so they are not retried), or None on network failure.
    """
    results: Dict[str, Dict[str, Any]] = {}
    for start in range(0, min(len(ips), BATCH_SIZE * MAX_BATCHES_PER_CALL), BATCH_SIZE):
        chunk = ips[start : start + BATCH_SIZE]
        try:
            async with async_timeout.timeout(10):
                async with session.post(BATCH_URL, json=chunk) as resp:
                    resp.raise_for_status()
                    entries = await resp.json()
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            _LOGGER.warning("ip-api.com geolocation lookup failed: %s", e)
            return results or None

        for entry in entries or []:
            ip = entry.get("query")
            if not ip:
                continue
            if entry.get("status") != "success":
                # Not locatable (private/reserved range, ...): cache as empty.
                results[ip] = {}
                continue
            geo: Dict[str, Any] = {}
            if entry.get("countryCode"):
                geo["country"] = entry["countryCode"]
            if entry.get("lat") is not None:
                geo["latitude"] = entry["lat"]
            if entry.get("lon") is not None:
                geo["longitude"] = entry["lon"]
            if entry.get("asname"):
                geo["as_name"] = entry["asname"]
            as_field = entry.get("as") or ""
            if as_field.startswith("AS"):
                try:
                    geo["as_number"] = int(as_field.split()[0][2:])
                except (ValueError, IndexError):
                    pass
            results[ip] = geo
    return results
