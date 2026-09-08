# CrowdSec LAPI Integration for Home Assistant

This is a custom integration for Home Assistant that connects to a CrowdSec Local API (LAPI) to monitor active security decisions. It provides a sensor to track bans and fires events when new decisions are made or existing ones expire, allowing you to build powerful security-focused automations.



## Features

-   **Active Decisions Sensor**: Provides a `sensor.crowdsec_active_decisions` entity whose state is the total count of current bans.
-   **Detailed Attributes**: The sensor's attributes contain a full list of all active decisions, including the banned IP/value, the reason for the ban (scenario), and its duration.
-   **Geolocation (opt-in)**: Each decision can be enriched with `country`, `latitude`, `longitude`, `as_name` and `as_number`, available both in the sensor attributes and in the event payloads. This also covers decisions created before installing this integration and manual `cscli decisions add` bans. Geolocation is **disabled by default**: no banned IP leaves Home Assistant unless you pick a provider, either in the setup form or later from the integration's **Configure** dialog. Each IP is resolved only once and cached while the decision is active, and only routable addresses are resolved: private, loopback and reserved ranges are never looked up and never sent anywhere.
    -   **Disabled** (default): no lookup at all.
    -   **Local GeoLite2 database file**: resolves the IPs offline against MaxMind `.mmdb` files, so nothing leaves Home Assistant. **No database is shipped with this integration, and none is downloaded**: the integration only adds the `maxminddb` reader library (about 100 KB, code only, no data), and opens, read-only, the files you put at one fixed place inside your configuration directory:

        | File | Size | Adds |
        |:---|---:|:---|
        | `/config/crowdsec/GeoLite2-City.mmdb` | 63 MB | `country`, `latitude`, `longitude` |
        | `/config/crowdsec/GeoLite2-ASN.mmdb` (optional) | 11 MB | `as_name`, `as_number` |

        These are the very files CrowdSec downloads into its own data directory (usually `/var/lib/crowdsec/data`) as soon as the `crowdsecurity/geoip-enrich` parser is installed, and refreshes on `cscli hub upgrade`: copy them from there, or download them from [MaxMind](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) with a free account (a new build is published twice a week). Home Assistant in a container does not see the CrowdSec filesystem, hence the copy. A file replaced on disk is detected and reopened on the next poll, without restarting Home Assistant. If the City file is missing, an error in the log says where it is expected and the decisions are simply left without geo data.

        The integration never downloads anything itself; to keep the files fresh without manual work, let a Home Assistant automation do it. The command below fetches CrowdSec's own copies (no account, no key), writes to a temporary name and renames at the end, so the integration never sees a half-written file; it picks the new one up on its next poll.

        ```yaml
        shell_command:
          crowdsec_geolite2_update: >-
            mkdir -p /config/crowdsec &&
            curl -fsSL -o /config/crowdsec/GeoLite2-City.mmdb.tmp https://hub-data.crowdsec.net/mmdb_update/GeoLite2-City.mmdb &&
            mv /config/crowdsec/GeoLite2-City.mmdb.tmp /config/crowdsec/GeoLite2-City.mmdb &&
            curl -fsSL -o /config/crowdsec/GeoLite2-ASN.mmdb.tmp https://hub-data.crowdsec.net/mmdb_update/GeoLite2-ASN.mmdb &&
            mv /config/crowdsec/GeoLite2-ASN.mmdb.tmp /config/crowdsec/GeoLite2-ASN.mmdb

        automation:
          - alias: CrowdSec GeoLite2 weekly update
            trigger:
              - platform: time
                at: "04:30:00"
            condition:
              - condition: time
                weekday: [mon]
            action:
              - service: shell_command.crowdsec_geolite2_update
        ```

        Run the command once from **Developer tools** > **Actions** to get the first copy. For databases straight from MaxMind (refreshed twice a week), use their download URL with your account id and license key instead; it delivers a `tar.gz` to extract.
    -   **ipquery.io**: remote lookup over **HTTPS** via [ipquery.io](https://ipquery.io), no API key. The banned IPs are sent to that third-party service, but on a ciphered connection. Quota: the service advertises an unlimited free tier and throttles with an HTTP 429 answer when it judges the traffic excessive, without publishing a figure; its bulk endpoint takes up to 10,000 IPs per request. The integration sends batches of 50 IPs and at most 5 batches per scan, each IP only once, so even an initial sync of 250 active bans fits in a single poll and the rest follows on the next ones.
    -   **ip-api.com**: remote lookup via the free [ip-api.com](https://ip-api.com) service, no API key. **Privacy note**: the free endpoint refuses HTTPS, so the banned IPs travel in clear text. Quota: the free tier is limited to 15 batch requests per minute, 100 IPs per batch, for non-commercial use, and answers HTTP 429 beyond that. The integration sends at most 5 batches per scan, each IP only once, so even an initial sync of 500 active bans fits in a single poll.
    -   Adding a provider is adding one file under `custom_components/crowdsec/geo/providers/`, holding a class decorated with `@register`: the interface lives in `geo/base.py`, the dropdown and the factory in `geo/registry.py`, and the data model exposed to cards and automations never changes.
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
    -   **Geolocation of banned IPs**: `Disabled` (default), the local GeoLite2 file, ipquery.io over HTTPS, or ip-api.com. See the [Geolocation](#features) feature above for the privacy implications.
4.  Click **Submit**. The integration will be set up, and a sensor entity will be created.
5.  The update frequency and the geolocation provider can be changed at any time from the integration's **Configure** button (the integration reloads automatically).

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
  | IP Address / Value | Country | Reason of Ban | Duration |
  |:---|:---|:---|:---|
  {% set decisions = state_attr('sensor.crowdsec_active_decisions', 'decisions') -%}
  {% if decisions %}
    {%- for decision in decisions -%}
  | `{{ decision.value }}` | {{ decision.country | default('?', true) }} | {{ decision.scenario }} | {{ decision.duration }} |
    {% endfor -%}
  {%- else -%}
  | No active decisions | | | |
  {%- endif %}
```

The `default('?', true)` filter keeps the card rendering a `?` instead of an error when the geo data is missing (geolocation disabled, private IPs, or a lookup that has not completed yet). With the coordinates you can even link each ban to a map — guard on `latitude` so rows without geo data fall back to plain text:

```yaml
| `{{ decision.value }}` | {% if decision.latitude is defined %}[{{ decision.country | default('?', true) }}](https://www.openstreetmap.org/?mlat={{ decision.latitude }}&mlon={{ decision.longitude }}#map=6/{{ decision.latitude }}/{{ decision.longitude }}){% else %}{{ decision.country | default('?', true) }}{% endif %} | {{ decision.scenario }} |
```
