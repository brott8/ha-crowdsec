# sensor.py
import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant import config_entries
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import CrowdSecApiClient
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Define event types as constants
EVENT_NEW_DECISION = "crowdsec_new_decision"
EVENT_DECISION_REMOVED = "crowdsec_decision_expired"

class CrowdSecCoordinator(DataUpdateCoordinator[List[Dict[str, Any]]]):
    """Coordinates fetching data from the CrowdSec LAPI."""

    def __init__(self, hass: HomeAssistant, api_client: CrowdSecApiClient):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api_client = api_client
        # Store the full decision objects from the last successful update
        self._known_decisions: Dict[int, Dict[str, Any]] = {}

    async def _async_update_data(self) -> List[Dict[str, Any]]:
        """Fetch data from API endpoint and detect changes."""
        decisions = await self.api_client.get_decisions()
        if decisions is None:
            # The API client will log the specific error
            raise UpdateFailed("Failed to communicate with CrowdSec LAPI.")

        current_decisions_map = {d['id']: d for d in decisions}
        current_ids = set(current_decisions_map.keys())
        known_ids = set(self._known_decisions.keys())

        # --- Detect and fire events for NEW decisions ---
        new_ids = current_ids - known_ids
        for dec_id in new_ids:
            new_decision = current_decisions_map[dec_id]
            _LOGGER.info("New CrowdSec decision: %s", new_decision['value'])
            self.hass.bus.async_fire(EVENT_NEW_DECISION, new_decision)

        # --- Detect and fire events for REMOVED decisions ---
        removed_ids = known_ids - current_ids
        for dec_id in removed_ids:
            # The data for the removed decision is in our stored _known_decisions
            removed_decision = self._known_decisions[dec_id]
            _LOGGER.info("CrowdSec decision removed: %s", removed_decision['value'])
            self.hass.bus.async_fire(EVENT_DECISION_REMOVED, removed_decision)

        # Update the state for the next poll and return data to entities
        self._known_decisions = current_decisions_map
        return decisions


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the CrowdSec sensor from a config entry."""
    session = hass.data[DOMAIN][entry.entry_id]["session"]
    api = CrowdSecApiClient(**entry.data, session=session)
    coordinator = CrowdSecCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    # Pass the config entry to the sensor so it can link to the device
    async_add_entities([CrowdSecSensor(coordinator, entry)])


class CrowdSecSensor(CoordinatorEntity[CrowdSecCoordinator], SensorEntity):
    """A sensor representing CrowdSec active decisions."""

    _attr_icon = "mdi:shield-bug"

    def __init__(self, coordinator: CrowdSecCoordinator, entry: config_entries.ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        # Unique ID for the sensor entity itself
        self._attr_unique_id = f"{entry.entry_id}_active_decisions"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "CrowdSec LAPI",
            "manufacturer": "CrowdSec",
            "model": "Local API",
            # "sw_version": coordinator.data.get("version", "N/A"),
            "entry_type": "service",
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "CrowdSec Active Decisions"

    @property
    def native_value(self) -> int:
        """Return the number of active decisions."""
        return len(self.coordinator.data) if self.coordinator.data else 0

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the decisions as attributes."""
        return {"decisions": self.coordinator.data or []}