DOMAIN = "crowdsec"
DEFAULT_PORT = 8080
DEFAULT_SCAN_INTERVAL = 60
CONF_SCHEME = "scheme"
CONF_SCAN_INTERVAL = "scan_interval"

# Geolocation of the banned IPs. Opt-in: disabled unless the user picks a
# provider. The providers themselves live in the geo package.
CONF_GEO_PROVIDER = "geo_provider"
GEO_PROVIDER_NONE = "none"
DEFAULT_GEO_PROVIDER = GEO_PROVIDER_NONE

# Event types
EVENT_NEW_DECISION = "crowdsec_new_decision"
EVENT_DECISION_REMOVED = "crowdsec_decision_expired"
# Lovelace card served by the integration
URL_BASE = "/crowdsec-card"
FALLBACK_VERSION = "0.0.0"
JSMODULES = [
    {"name": "CrowdSec Card", "filename": "crowdsec-card.js", "resource": True},
    {"name": "CrowdSec world map", "filename": "world-map.js", "resource": False},
]
