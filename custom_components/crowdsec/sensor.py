# sensor.py
import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant import config_entries
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import device_registry as dr

from .api import CrowdSecApiClient

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, EVENT_NEW_DECISION, EVENT_DECISION_REMOVED

_LOGGER = logging.getLogger(__name__)

class CrowdSecCoordinator(DataUpdateCoordinator[List[Dict[str, Any]]]):
    """Coordinates fetching data from the CrowdSec LAPI."""

    def __init__(self, hass: HomeAssistant, api_client: CrowdSecApiClient, entry: config_entries.ConfigEntry):
        """Initialize the coordinator."""
        # Get the scan_interval from the entry object that was passed in.
        scan_interval = entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api_client = api_client
        self.entry = entry # Store the config entry
        # Store the full decision objects from the last successful update
        self._known_decisions: Dict[int, Dict[str, Any]] = {}

    async def _async_update_data(self) -> list[dict[str, any]]:
        """Fetch data from API endpoint and detect changes."""
        # Fetch decisions FIRST. This should always happen.
        decisions = await self.api_client.get_decisions() or []

        # Always perform the comparison logic to see if anything changed.
        current_decisions_map = {d['id']: d for d in decisions}
        current_ids = set(current_decisions_map.keys())
        known_ids = set(self._known_decisions.keys())
        new_ids = current_ids - known_ids
        removed_ids = known_ids - current_ids

        # If there are events to fire, find the device and fire them.
        if new_ids or removed_ids:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self.entry.entry_id)}
            )

            if not device:
                _LOGGER.warning("Device not found, cannot fire events for this update.")
            else:
                device_id = device.id
                # Fire events for NEW decisions
                for dec_id in new_ids:
                    new_decision = current_decisions_map[dec_id]
                    # Create the payload with the device_id
                    event_payload = {**new_decision, "device_id": device_id}
                    # Pass the correct event_payload here
                    self.hass.bus.async_fire(EVENT_NEW_DECISION, event_payload)
                    _LOGGER.debug("Fired new_decision event for %s", new_decision['value'])

                # Fire events for REMOVED decisions
                for dec_id in removed_ids:
                    removed_decision = self._known_decisions[dec_id]
                    # Create the payload with the device_id
                    event_payload = {**removed_decision, "device_id": device_id}
                    # Pass the correct event_payload here
                    self.hass.bus.async_fire(EVENT_DECISION_REMOVED, event_payload)
                    _LOGGER.debug("Fired decision_removed event for %s", removed_decision['value'])

        # ALWAYS update the internal state for the next poll.
        self._known_decisions = current_decisions_map
        
        # Return the data for sensor entities.
        return decisions

async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CrowdSec sensor from a config entry."""
    # Retrieve the coordinator that was created in __init__.py
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CrowdSecSensor(coordinator, entry)])


class CrowdSecSensor(CoordinatorEntity[CrowdSecCoordinator], SensorEntity):
    """A sensor representing CrowdSec active decisions."""

    _attr_icon = "mdi:shield-bug"

    def __init__(self, coordinator: CrowdSecCoordinator, entry: config_entries.ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        # Unique ID for the sensor entity itself
        self._attr_unique_id = f"{entry.entry_id}_active_decisions"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

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