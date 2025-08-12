"""Provides device triggers for CrowdSec."""
from __future__ import annotations

import voluptuous as vol
from typing import Any

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
# Add Event to the imports from homeassistant.core
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, Event
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA

from .const import DOMAIN, EVENT_DECISION_REMOVED, EVENT_NEW_DECISION

# This maps the internal trigger type string to the actual event constant.
TRIGGER_TYPE_TO_EVENT = {
    "new_decision": EVENT_NEW_DECISION,
    "decision_removed": EVENT_DECISION_REMOVED,
}

# This ensures you only have to define the trigger types in one place.
TRIGGER_TYPES = set(TRIGGER_TYPE_TO_EVENT.keys())

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)

async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for CrowdSec devices."""
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]

async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    event_type = TRIGGER_TYPE_TO_EVENT[config[CONF_TYPE]]
    device_id = config[CONF_DEVICE_ID]

    async def handle_event(event: Event) -> None:
        """Handle the event and run the action."""
        # Manually filter the event: check if it's for our device.
        if event.data.get("device_id") != device_id:
            return

        # This passes the event's data to the action, making it available
        # in templates as 'trigger.event.data'.
        await action({**trigger_info, "trigger_data": event.data}, context=event.context)

    return hass.bus.async_listen(event_type, handle_event)
