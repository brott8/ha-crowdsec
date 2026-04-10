# api.py
import asyncio
import logging
from typing import List, Dict, Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

class CrowdSecApiClient:
    """A client for the CrowdSec LAPI."""

    def __init__(self, scheme: str, host: str, port: int, api_key: str, unique_id: str, session: aiohttp.ClientSession):
        """Initialize the API client."""
        self._url = f"{scheme}://{host}:{port}/v1/decisions?origins=crowdsec,cscli"
        self._headers = {"X-Api-Key": api_key}
        self.session = session
        self.unique_id = unique_id
        self._geo_cache: Dict[str, str] = {}  # IP → country code Cache

    async def _enrich_with_geo(self, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add country info to decisions via ip-api.com batch endpoint."""
        # Nur IPs die noch nicht im Cache sind
        ips_to_lookup = list({
            d["value"] for d in decisions
            if d.get("scope") == "Ip" and d["value"] not in self._geo_cache
        })

        if ips_to_lookup:
            try:
                with async_timeout.timeout(10):
                    async with self.session.post(
                        "http://ip-api.com/batch?fields=query,countryCode,country",
                        json=[{"query": ip} for ip in ips_to_lookup]
                    ) as resp:
                        resp.raise_for_status()
                        results = await resp.json()
                        for r in results:
                            self._geo_cache[r["query"]] = {
                                "country_code": r.get("countryCode", ""),
                                "country": r.get("country", ""),
                            }
            except Exception as e:
                _LOGGER.warning("GeoIP lookup failed: %s", e)

        # Decisions mit Geo-Daten anreichern
        enriched = []
        for d in decisions:
            geo = self._geo_cache.get(d.get("value"), {})
            enriched.append({**d, **geo})
        return enriched

    async def get_decisions(self) -> List[Dict[str, Any]]:
        """Fetch active decisions from the LAPI."""
        try:
            with async_timeout.timeout(10):
                async with self.session.get(self._url, headers=self._headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    decisions = data if data is not None else []
                    return await self._enrich_with_geo(decisions)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout connecting to CrowdSec LAPI at %s", self._url)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching CrowdSec decisions: %s", e)

        return None
