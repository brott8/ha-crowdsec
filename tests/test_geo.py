"""Tests for the opt-in geolocation of the CrowdSec integration."""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crowdsec.const import (
    CONF_GEO_PROVIDER,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    GEO_PROVIDER_NONE,
)
from custom_components.crowdsec.geo import (
    PROVIDERS,
    as_number,
    async_create_geo_provider,
    provider_classes,
    provider_options,
)
from custom_components.crowdsec.geo.providers.geolite2_file import GeoLite2FileGeoProvider
from custom_components.crowdsec.geo.providers.ip_api import IpApiGeoProvider
from custom_components.crowdsec.geo.providers.ipquery import IpQueryGeoProvider

ENTRY_DATA = {
    "host": "lapi.local",
    "port": 8080,
    "api_key": "secret",
    "scheme": "http",
    "scan_interval": 60,
}

DECISIONS = [
    {"id": 1, "scope": "Ip", "value": "1.2.3.4", "scenario": "ssh-bf", "duration": "1h", "origin": "crowdsec", "type": "ban"},
    {"id": 2, "scope": "Range", "value": "5.6.7.0/24", "scenario": "http-probing", "duration": "4h", "origin": "crowdsec", "type": "ban"},
    {"id": 3, "scope": "Ip", "value": "192.168.1.10", "scenario": "local", "duration": "1h", "origin": "cscli", "type": "ban"},
]

IP_API_RESPONSE = [
    {"status": "success", "countryCode": "FR", "lat": 48.85, "lon": 2.35, "as": "AS16276 OVH SAS", "asname": "OVH", "query": "1.2.3.4"},
    {"status": "success", "countryCode": "DE", "lat": 52.5, "lon": 13.4, "as": "AS3320 Deutsche Telekom AG", "asname": "DTAG", "query": "5.6.7.0"},
]

IPQUERY_RESPONSE = [
    {"ip": "1.2.3.4", "isp": {"asn": "AS16276", "org": "OVH SAS", "isp": "OVH"},
     "location": {"country_code": "FR", "latitude": 48.85, "longitude": 2.35}},
    {"ip": "5.6.7.0", "isp": {"asn": "AS6805", "org": "Telefonica Germany", "isp": "Telefonica"},
     "location": {"country_code": "DE", "latitude": 48.17, "longitude": 11.52}},
]


def _patch_decisions(decisions):
    """Fake LAPI answering fresh copies on every poll, as the real one does."""
    return patch(
        "custom_components.crowdsec.api.CrowdSecApiClient.get_decisions",
        AsyncMock(side_effect=lambda: [dict(d) for d in decisions]),
    )


def _sensor(hass, entry):
    """State of the decisions sensor, found through its unique id."""
    from homeassistant.helpers import entity_registry as er
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_active_decisions"
    )
    assert entity_id, "sensor not registered"
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


# ------------------------------------------------------------- registry ---


def test_registry_holds_the_three_providers():
    assert set(PROVIDERS) == {"geolite2_file", "ipquery", "ip_api"}


def test_dropdown_lists_disabled_then_local_then_ciphered():
    assert [o["value"] for o in provider_options()] == [
        GEO_PROVIDER_NONE,
        "geolite2_file",
        "ipquery",
        "ip_api",
    ]
    assert all(o["label"] for o in provider_options())


def test_provider_classes_are_ordered_by_priority():
    assert provider_classes() == [
        GeoLite2FileGeoProvider,
        IpQueryGeoProvider,
        IpApiGeoProvider,
    ]


async def test_factory_none_and_unknown(hass):
    assert await async_create_geo_provider(hass, GEO_PROVIDER_NONE) is None
    assert await async_create_geo_provider(hass, "bogus") is None
    assert isinstance(await async_create_geo_provider(hass, "ip_api"), IpApiGeoProvider)
    assert isinstance(await async_create_geo_provider(hass, "ipquery"), IpQueryGeoProvider)
    assert isinstance(
        await async_create_geo_provider(hass, "geolite2_file"), GeoLite2FileGeoProvider
    )


async def test_factory_passes_the_entry_settings(hass):
    provider = await async_create_geo_provider(hass, "geolite2_file", {"anything": 1})
    assert provider.options == {"anything": 1}


@pytest.mark.parametrize(
    ("value", "expected"),
    [("AS16276 OVH SAS", 16276), ("AS0", None), (3320, None if False else 3320), (0, None), (None, None), ("", None)],
)
def test_as_number(value, expected):
    assert as_number(value) == expected


# -------------------------------------------------------- ip-api.com -----


def test_ip_api_parses_an_entry():
    assert IpApiGeoProvider._parse_entry(None, IP_API_RESPONSE[0]) == {
        "country": "FR", "latitude": 48.85, "longitude": 2.35,
        "as_name": "OVH", "as_number": 16276,
    }


def test_ip_api_failed_entry_is_empty():
    assert IpApiGeoProvider._parse_entry(None, {"status": "fail", "query": "10.0.0.1"}) == {}


async def test_ip_api_lookup(hass, aioclient_mock):
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, json=IP_API_RESPONSE)
    results = await IpApiGeoProvider(hass).async_lookup_ips(["1.2.3.4", "5.6.7.0"])
    assert results["1.2.3.4"]["country"] == "FR"
    assert results["5.6.7.0"]["as_number"] == 3320
    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][2] == ["1.2.3.4", "5.6.7.0"]


async def test_ip_api_lookup_network_failure(hass, aioclient_mock):
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, status=500)
    assert await IpApiGeoProvider(hass).async_lookup_ips(["1.2.3.4"]) is None


# --------------------------------------------------------- ipquery.io ----


def test_ipquery_parses_an_entry():
    assert IpQueryGeoProvider._parse_entry(None, IPQUERY_RESPONSE[0]) == {
        "country": "FR", "latitude": 48.85, "longitude": 2.35,
        "as_name": "OVH SAS", "as_number": 16276,
    }


def test_ipquery_unlocatable_entry_is_empty():
    """An unlocatable IP answers an empty country and junk coordinates."""
    entry = {"ip": "192.168.1.10", "isp": {"asn": "AS0", "org": "", "isp": ""},
             "location": {"country_code": "", "latitude": 0.0131, "longitude": -0.0121}}
    assert IpQueryGeoProvider._parse_entry(None, entry) == {}


def test_ipquery_uses_https():
    method, url, body = IpQueryGeoProvider._request(
        IpQueryGeoProvider.__new__(IpQueryGeoProvider), ["1.2.3.4", "5.6.7.0"]
    )
    assert method == "GET"
    assert url.startswith("https://")
    assert "1.2.3.4,5.6.7.0" in url
    assert body is None


async def test_ipquery_lookup(hass, aioclient_mock):
    aioclient_mock.get(
        f"{IpQueryGeoProvider.BASE_URL}1.2.3.4,5.6.7.0?format=json", json=IPQUERY_RESPONSE
    )
    results = await IpQueryGeoProvider(hass).async_lookup_ips(["1.2.3.4", "5.6.7.0"])
    assert results["1.2.3.4"]["country"] == "FR"
    assert results["5.6.7.0"]["as_number"] == 6805
    assert aioclient_mock.call_count == 1


# ------------------------------------------------- local GeoLite2 file ---


class _FakeReader:
    """Stand-in for a maxminddb reader."""

    def __init__(self, database_type, records):
        self._database_type = database_type
        self._records = records
        self.closed = False

    def metadata(self):
        return SimpleNamespace(database_type=self._database_type)

    def get(self, ip):
        if ip == "not-an-ip":
            raise ValueError("invalid address")
        return self._records.get(ip)

    def close(self):
        self.closed = True


CITY_RECORDS = {"1.2.3.4": {"country": {"iso_code": "FR"}, "location": {"latitude": 48.85, "longitude": 2.35}}}
ASN_RECORDS = {"1.2.3.4": {"autonomous_system_number": 16276, "autonomous_system_organization": "OVH SAS"}}


def _fake_maxminddb():
    def open_database(path):
        if "ASN" in path:
            return _FakeReader("GeoLite2-ASN", ASN_RECORDS)
        return _FakeReader("GeoLite2-City", CITY_RECORDS)

    return SimpleNamespace(
        open_database=open_database,
        InvalidDatabaseError=type("InvalidDatabaseError", (Exception,), {}),
    )


@pytest.fixture
def geolite_dir(hass):
    """The fixed database folder, emptied before and after the test.

    The test configuration directory is shared by every test, so stand-in
    files left behind would leak into the next one.
    """
    import shutil
    directory = hass.config.path("crowdsec")
    shutil.rmtree(directory, ignore_errors=True)
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _write_databases(hass, asn=True):
    """Create empty stand-ins at the fixed location inside the config dir."""
    import os
    directory = hass.config.path("crowdsec")
    os.makedirs(directory, exist_ok=True)
    names = ["GeoLite2-City.mmdb"] + (["GeoLite2-ASN.mmdb"] if asn else [])
    for name in names:
        open(os.path.join(directory, name), "wb").close()
    return directory


def test_local_parses_city_and_asn_records():
    assert GeoLite2FileGeoProvider._parse_location(CITY_RECORDS["1.2.3.4"]) == {
        "country": "FR", "latitude": 48.85, "longitude": 2.35,
    }
    assert GeoLite2FileGeoProvider._parse_asn(ASN_RECORDS["1.2.3.4"]) == {
        "as_name": "OVH SAS", "as_number": 16276,
    }
    assert GeoLite2FileGeoProvider._parse_location(None) == {}
    assert GeoLite2FileGeoProvider._parse_asn(None) == {}


def test_local_falls_back_to_the_registered_country():
    record = {"registered_country": {"iso_code": "NL"}}
    assert GeoLite2FileGeoProvider._parse_location(record) == {"country": "NL"}


async def test_local_expected_paths(hass):
    provider = GeoLite2FileGeoProvider(hass)
    assert provider.location_path == hass.config.path("crowdsec", "GeoLite2-City.mmdb")
    assert provider.asn_path == hass.config.path("crowdsec", "GeoLite2-ASN.mmdb")


async def test_local_lookup_reads_both_databases(hass, aioclient_mock, geolite_dir):
    _write_databases(hass)
    provider = GeoLite2FileGeoProvider(hass)

    with patch.dict(sys.modules, {"maxminddb": _fake_maxminddb()}):
        results = await provider.async_lookup_ips(["1.2.3.4", "9.9.9.9"])

    assert results["1.2.3.4"] == {
        "country": "FR", "latitude": 48.85, "longitude": 2.35,
        "as_name": "OVH SAS", "as_number": 16276,
    }
    # An address absent from the databases is cached as a miss.
    assert results["9.9.9.9"] == {}
    # Nothing was sent anywhere.
    assert aioclient_mock.call_count == 0
    provider.close()


async def test_local_lookup_city_only(hass, geolite_dir):
    _write_databases(hass, asn=False)
    provider = GeoLite2FileGeoProvider(hass)
    with patch.dict(sys.modules, {"maxminddb": _fake_maxminddb()}):
        results = await provider.async_lookup_ips(["1.2.3.4"])
    assert results["1.2.3.4"] == {"country": "FR", "latitude": 48.85, "longitude": 2.35}


async def test_local_lookup_without_database_is_unavailable(hass, geolite_dir):
    provider = GeoLite2FileGeoProvider(hass)
    with patch.dict(sys.modules, {"maxminddb": _fake_maxminddb()}):
        assert await provider.async_lookup_ips(["1.2.3.4"]) is None


async def test_local_lookup_ignores_an_invalid_address(hass, geolite_dir):
    _write_databases(hass)
    provider = GeoLite2FileGeoProvider(hass)
    with patch.dict(sys.modules, {"maxminddb": _fake_maxminddb()}):
        results = await provider.async_lookup_ips(["not-an-ip"])
    assert results == {"not-an-ip": {}}


async def test_local_reopens_a_replaced_database(hass, geolite_dir):
    import os
    directory = _write_databases(hass, asn=False)
    provider = GeoLite2FileGeoProvider(hass)
    with patch.dict(sys.modules, {"maxminddb": _fake_maxminddb()}):
        await provider.async_lookup_ips(["1.2.3.4"])
        first_reader = provider._location_reader
        # The ASN file appears later: noticed on the next poll.
        with open(os.path.join(directory, "GeoLite2-ASN.mmdb"), "wb") as f:
            f.write(b"x")
        results = await provider.async_lookup_ips(["1.2.3.4"])
    assert first_reader.closed
    assert results["1.2.3.4"]["as_number"] == 16276


# --------------------------------------------------------- setup + sensor ---


async def _refresh(hass, entry):
    """Run one poll: the coordinator has no first refresh at setup."""
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()


async def _setup(hass, data, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options or {}, unique_id="lapi.local:8080", title="lapi.local")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _refresh(hass, entry)
    return entry


async def test_default_is_no_lookup(hass, aioclient_mock):
    """Default: no provider, nothing is sent anywhere, decisions untouched."""
    with _patch_decisions(DECISIONS):
        entry = await _setup(hass, ENTRY_DATA)
    state = _sensor(hass, entry)
    assert state.state == "3"
    assert aioclient_mock.call_count == 0
    assert all("country" not in d for d in state.attributes["decisions"])


async def test_enrichment_cache_and_private_addresses(hass, aioclient_mock):
    """The provider enriches once per IP and private ranges are never sent."""
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, json=IP_API_RESPONSE)
    with _patch_decisions(DECISIONS):
        entry = await _setup(hass, {**ENTRY_DATA, CONF_GEO_PROVIDER: "ip_api"})
        state = _sensor(hass, entry)
        by_value = {d["value"]: d for d in state.attributes["decisions"]}
        assert by_value["1.2.3.4"]["country"] == "FR"
        assert by_value["1.2.3.4"]["latitude"] == 48.85
        assert by_value["1.2.3.4"]["as_number"] == 16276
        # A banned range is resolved through its network address.
        assert by_value["5.6.7.0/24"]["country"] == "DE"
        # The private address is neither enriched nor sent out.
        assert "country" not in by_value["192.168.1.10"]
        assert aioclient_mock.call_count == 1
        assert set(aioclient_mock.mock_calls[0][2]) == {"1.2.3.4", "5.6.7.0"}

        # Second poll: everything cached, no new request.
        await _refresh(hass, entry)
        assert aioclient_mock.call_count == 1
        assert _sensor(hass, entry).attributes["decisions"][0]["country"] == "FR"


async def test_new_decision_event_carries_geo(hass, aioclient_mock):
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, json=IP_API_RESPONSE)
    events = []
    hass.bus.async_listen("crowdsec_new_decision", lambda e: events.append(e))
    with _patch_decisions(DECISIONS):
        await _setup(hass, {**ENTRY_DATA, CONF_GEO_PROVIDER: "ip_api"})
    by_value = {e.data["value"]: e.data for e in events}
    assert by_value["1.2.3.4"]["country"] == "FR"
    assert "device_id" in by_value["1.2.3.4"]


async def test_lookup_failure_keeps_decisions(hass, aioclient_mock):
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, status=503)
    with _patch_decisions(DECISIONS):
        entry = await _setup(hass, {**ENTRY_DATA, CONF_GEO_PROVIDER: "ip_api"})
    state = _sensor(hass, entry)
    assert state.state == "3"
    assert all("country" not in d for d in state.attributes["decisions"])


async def test_setup_with_the_local_provider(hass, aioclient_mock, geolite_dir):
    _write_databases(hass)
    with patch.dict(sys.modules, {"maxminddb": _fake_maxminddb()}), _patch_decisions(DECISIONS):
        entry = await _setup(hass, {**ENTRY_DATA, CONF_GEO_PROVIDER: "geolite2_file"})
        state = _sensor(hass, entry)
    by_value = {d["value"]: d for d in state.attributes["decisions"]}
    assert by_value["1.2.3.4"]["country"] == "FR"
    assert by_value["1.2.3.4"]["as_name"] == "OVH SAS"
    assert aioclient_mock.call_count == 0


# ------------------------------------------------------------ config flow ---


async def test_config_flow_defaults_to_none(hass):
    with _patch_decisions([]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] == FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "lapi.local", "api_key": "secret"}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GEO_PROVIDER] == GEO_PROVIDER_NONE
    assert result["data"]["port"] == 8080


@pytest.mark.parametrize("provider", ["geolite2_file", "ipquery", "ip_api"])
async def test_config_flow_opt_in(hass, provider):
    with _patch_decisions([]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "lapi.local", "api_key": "secret", CONF_GEO_PROVIDER: provider}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GEO_PROVIDER] == provider


async def test_config_flow_rejects_unknown_provider(hass):
    with _patch_decisions([]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        with pytest.raises(Exception):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {"host": "lapi.local", "api_key": "secret", CONF_GEO_PROVIDER: "bogus"}
            )


async def test_options_flow_enables_provider_and_reloads(hass, aioclient_mock):
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, json=IP_API_RESPONSE)
    with _patch_decisions(DECISIONS):
        entry = await _setup(hass, ENTRY_DATA)
        assert aioclient_mock.call_count == 0

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 30, CONF_GEO_PROVIDER: "ip_api"}
        )
        await hass.async_block_till_done()
        await _refresh(hass, entry)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_GEO_PROVIDER] == "ip_api"
    assert entry.options[CONF_SCAN_INTERVAL] == 30
    # The entry reloaded with the provider enabled: one lookup happened
    assert aioclient_mock.call_count == 1
    assert hass.data[DOMAIN][entry.entry_id].update_interval.total_seconds() == 30
    assert _sensor(hass, entry).attributes["decisions"][0]["country"] == "FR"


async def test_options_flow_disables_provider(hass, aioclient_mock):
    aioclient_mock.post(IpApiGeoProvider.BATCH_URL, json=IP_API_RESPONSE)
    with _patch_decisions(DECISIONS):
        entry = await _setup(hass, {**ENTRY_DATA, CONF_GEO_PROVIDER: "ip_api"})
        assert aioclient_mock.call_count == 1
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 60, CONF_GEO_PROVIDER: GEO_PROVIDER_NONE}
        )
        await hass.async_block_till_done()
        await _refresh(hass, entry)
    assert aioclient_mock.call_count == 1
    assert hass.data[DOMAIN][entry.entry_id].geo_provider is None
    assert all("country" not in d for d in _sensor(hass, entry).attributes["decisions"])
