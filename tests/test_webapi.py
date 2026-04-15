import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from argo_automation_cpas.webapi import WebAPI

from conftest import prime_settings


@pytest.fixture
def settings():
    return prime_settings(SimpleNamespace(
        general=SimpleNamespace(
            request_timeout=30.0,
            verify_ssl=True,
            retries=3,
            retry_delay=1.0,
        ),
        automation=SimpleNamespace(tenants=["TENANT-A"]),
        webapi=SimpleNamespace(
            host="api.example.com",
            url="https://api.example.com",
            url_api_config="/api/v2/feeds/topology",
            url_api_integrations="/api/v3/integrations/components/{component}/by-tenant-name/{tenant_name}/refresh",
            token_component_admin="admin-tok",
            components=["connectors", "sensu"],
            tokens_spool="/tmp/webapi_tokens.json",
        ),
    ))


@pytest.fixture
def svc(settings):
    with patch("argo_automation_cpas.webapi.SessionWithRetry"):
        s = WebAPI()
    s.session = MagicMock(
        http_get=AsyncMock(),
        http_post=AsyncMock(),
        close=AsyncMock(),
    )
    return s


# ---------------------------------------------------------------------------
# fetch_topology_config
# ---------------------------------------------------------------------------

async def test_fetch_topology_config_success(svc):
    svc.session.http_get.return_value = {
        "data": [{"type": "GOCDB", "feed_url": "https://gocdb.example.com/feeds"}]
    }

    result = await svc.fetch_topology_config("/api/v2/feeds/topology")

    assert result == {
        "connector_tenant_topo_type": "GOCDB",
        "connector_tenant_topo_feed": "https://gocdb.example.com/feeds",
    }


async def test_fetch_topology_config_with_token(svc):
    svc.session.http_get.return_value = {"data": [{"type": "CSV"}]}

    result = await svc.fetch_topology_config("/api/v2/feeds/topology", token="comp-tok")

    assert result == {"connector_tenant_topo_type": "CSV"}
    call_kwargs = svc.session.http_get.call_args
    assert call_kwargs.kwargs["headers"]["x-api-key"] == "comp-tok"
    assert call_kwargs.kwargs["headers"]["Accept"] == "application/json"


async def test_fetch_topology_config_empty_data(svc):
    svc.session.http_get.return_value = {"data": []}

    result = await svc.fetch_topology_config("/api/v2/feeds/topology")

    assert result == {}


async def test_fetch_topology_config_connection_error(svc):
    svc.session.http_get.side_effect = aiohttp.ClientConnectionError("fail")

    result = await svc.fetch_topology_config("/api/v2/feeds/topology")

    assert result == {}


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------

async def test_refresh_tokens_success(svc):
    svc.session.http_post.return_value = {"data": {"api_key": "tok-abc"}}

    tokens = await svc.refresh_tokens()

    assert tokens["TENANT-A"]["connectors"] == "tok-abc"
    assert tokens["TENANT-A"]["sensu"] == "tok-abc"
    assert svc.session.http_post.call_count == 2


async def test_refresh_tokens_partial_failure(svc):
    call_count = 0

    async def mock_post(url, headers=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise aiohttp.ClientConnectionError("fail")
        return {"data": {"api_key": "tok-sensu"}}

    svc.session.http_post = mock_post

    tokens = await svc.refresh_tokens()

    assert "connectors" not in tokens["TENANT-A"]
    assert tokens["TENANT-A"]["sensu"] == "tok-sensu"


# ---------------------------------------------------------------------------
# save_tokens
# ---------------------------------------------------------------------------

def test_save_tokens(tmp_path):
    path = str(tmp_path / "tokens.json")
    data = {"TENANT-A": {"connectors": "tok-1"}}

    WebAPI.save_tokens(data, path)

    with open(path) as fh:
        assert json.load(fh) == data


# ---------------------------------------------------------------------------
# find_connector_token
# ---------------------------------------------------------------------------

def test_find_connector_token_found():
    tokens = {"T1": {"connectors": "tok-conn", "sensu": "tok-sensu"}}
    assert WebAPI.find_connector_token(tokens) == "tok-conn"


def test_find_connector_token_not_found():
    tokens = {"T1": {"sensu": "tok-sensu", "poem": "tok-poem"}}
    assert WebAPI.find_connector_token(tokens) is None


def test_find_connector_token_empty():
    assert WebAPI.find_connector_token({}) is None


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@patch.object(WebAPI, "fetch_topology_config", new_callable=AsyncMock)
@patch.object(WebAPI, "save_tokens")
@patch.object(WebAPI, "refresh_tokens", new_callable=AsyncMock)
async def test_run_refreshes_and_fetches_config(mock_refresh, mock_save, mock_fetch, svc):
    mock_refresh.return_value = {"TENANT-A": {"connectors": "conn-tok", "sensu": "sensu-tok"}}
    mock_fetch.return_value = {"connector_tenant_topo_type": "GOCDB"}

    await svc.run()

    mock_refresh.assert_called_once()
    mock_save.assert_called_once_with(
        {"TENANT-A": {"connectors": "conn-tok", "sensu": "sensu-tok"}},
        svc.settings.webapi.tokens_spool,
    )
    mock_fetch.assert_called_once_with(svc.settings.webapi.url_api_config, token="conn-tok")
    svc.session.close.assert_called_once()


@patch.object(WebAPI, "fetch_topology_config", new_callable=AsyncMock)
@patch.object(WebAPI, "save_tokens")
@patch.object(WebAPI, "refresh_tokens", new_callable=AsyncMock)
async def test_run_no_tokens_skips_save_and_config(mock_refresh, mock_save, mock_fetch, svc):
    mock_refresh.return_value = {"TENANT-A": {}}

    await svc.run()

    mock_save.assert_not_called()
    mock_fetch.assert_not_called()
    svc.session.close.assert_called_once()
