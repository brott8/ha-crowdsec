# CrowdSec LAPI Integration for Home Assistant

This is a custom integration for Home Assistant that connects to a CrowdSec Local API (LAPI) to monitor active security decisions. It provides a sensor to track bans and fires events when new decisions are made or existing ones expire, allowing you to build powerful security-focused automations.



## Features

-   **Active Decisions Sensor**: Provides a `sensor.crowdsec_active_decisions` entity whose state is the total count of current bans.
-   **Detailed Attributes**: The sensor's attributes contain a full list of all active decisions, including the banned IP/value, the reason for the ban (scenario), and its duration.
-   **Real-time Event Notifications**:
    -   Fires a `crowdsec_new_decision` event whenever a new ban is detected by the integration.
    -   Fires a `crowdsec_decision_removed` event whenever a ban expires or is manually removed.
-   **Configurable Update Frequency**: You can set the polling interval to meet your needs directly from the integration's configuration in the UI.
-   **Easy Setup**: Simple configuration flow to connect to your CrowdSec LAPI instance using either HTTP or HTTPS.

## Installation

1.  **HACS (Recommended)**:
    -   Go to HACS.
    -   Find the "CrowdSec LAPI" integration in the list and click **Install**.

2.  **Manual Installation**:
    -   Copy the `crowdsec` directory from this repository.
    -   Place it inside the `custom_components` folder in your Home Assistant configuration directory.

After either installation method, **restart Home Assistant**.

## Configuration

1.  Go to **Settings** > **Devices & Services**.
2.  Click **+ Add Integration** and search for **CrowdSec**.
3.  Enter the required details for your CrowdSec LAPI instance:
    -   **Host**: The IP address or hostname of your CrowdSec LAPI.
    -   **Port**: The port for the LAPI (usually `8080`).
    -   **API Key**: The API key for your bouncer, which you can generate with `cscli bouncers add homeassistant`.
    -   **Scheme**: Select `http` or `https`.
    -   **Scan Interval**: How often (in seconds) to check for new decisions.
4.  Click **Submit**. The integration will be set up, and a sensor entity will be created.

## Usage

### Automation Examples

The real power of this integration comes from using the events in your automations.

#### **Notify on a New Ban**

This automation sends a persistent notification to your mobile device whenever a new IP is banned.

```yaml
alias: Notify on New CrowdSec Ban
description: "Sends a notification when a new IP is banned"
trigger:
  - platform: event
    event_type: crowdsec_new_decision
condition: []
action:
  - service: notify.persistent_notification
    data:
      title: "New IP Banned by CrowdSec"
      message: "IP: {{ trigger.event.data.value }} for {{ trigger.event.data.duration }}. Reason: {{ trigger.event.data.scenario }}."
mode: single
```

#### **Lovelace Dashboard Card**

You can easily display the list of active decisions on your dashboard using a Markdown card.

```yaml
type: markdown
title: CrowdSec Active Decisions
content: |
  | IP Address / Value | Reason of Ban | Duration |
  |:---|:---|:---|
  {% set decisions = state_attr('sensor.crowdsec_active_decisions', 'decisions') -%}
  {% if decisions is iterable and decisions is not none %}
    {%- for decision in decisions -%}
  | {{ decision.value }} | {{ decision.scenario }} | {{ decision.duration }} |
    {% endfor -%}
  {%- else -%}
  | No active decisions | | |
  {%- endif %}
```
