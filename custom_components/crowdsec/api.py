# api.py
import asyncio
import logging
from typing import List, Dict, Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

class CrowdSecApiClient:
    """A client for the CrowdSec LAPI."""

    def __init__(self, scheme: str, host: str, port: int, api_key: str, session: aiohttp.ClientSession):
        """Initialize the API client."""
        self._url = f"{scheme}://{host}:{port}/v1/decisions?origins=crowdsec,cscli"
        self._headers = {"X-Api-Key": api_key}
        self.session = session

    async def get_decisions(self) -> List[Dict[str, Any]]:
        """Fetch active decisions from the LAPI."""
        try:
            with async_timeout.timeout(10):
                async with self.session.get(self._url, headers=self._headers) as resp:
                    resp.raise_for_status() # Aiohttp's way to raise on 4xx/5xx
                    return await resp.json()
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout connecting to CrowdSec LAPI at %s", self._url)
        except aiohttp.ClientError as e:
            # This will catch HTTP errors and connection issues
            _LOGGER.error("Error fetching CrowdSec decisions: %s", e)
        
        # Return an empty list on failure so the coordinator can handle it
        return []