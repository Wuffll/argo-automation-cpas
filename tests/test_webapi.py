import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from argo_automation_cpas.webapi import WebAPI


@pytest.fixture
def settings():
    return SimpleNamespace(
        request_timeout=30.0,
        verify_ssl=True,
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
    )


def _mock_session(method, status=200, json_data=None, raise_error=None):
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data or {})

    if raise_error:
        response.raise_for_status = MagicMock(side_effect=raise_error)
    else:
        response.raise_for_status = MagicMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    getattr(session, method).return_value = cm
    return session


# ---------------------------------------------------------------------------
# fetch_topology_config
# ---------------------------------------------------------------------------

async def test_fetch_topology_config_success(settings):
    session = _mock_session("get", json_data={
        "data": [{"type": "GOCDB", "feed_url": "https://gocdb.example.com/feeds"}]
    })

    svc = WebAPI(settings)
    result = await svc.fetch_topology_config(session, "/api/v2/feeds/topology")

    assert result == {
        "connector_tenant_topo_type": "GOCDB",
        "connector_tenant_topo_feed": "https://gocdb.example.com/feeds",
    }


async def test_fetch_topology_config_with_token(settings):
    session = _mock_session("get", json_data={"data": [{"type": "CSV"}]})

    svc = WebAPI(settings)
    result = await svc.fetch_topology_config(session, "/api/v2/feeds/topology", token="comp-tok")

    assert result == {"connector_tenant_topo_type": "CSV"}
    call_kwargs = session.get.call_args
    assert call_kwargs.kwargs["headers"]["x-api-key"] == "comp-tok"
    assert call_kwargs.kwargs["headers"]["Accept"] == "application/json"


async def test_fetch_topology_config_empty_data(settings):
    session = _mock_session("get", json_data={"data": []})

    svc = WebAPI(settings)
    result = await svc.fetch_topology_config(session, "/api/v2/feeds/topology")

    assert result == {}


async def test_fetch_topology_config_connection_error(settings):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("fail"))
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get.return_value = cm

    svc = WebAPI(settings)
    result = await svc.fetch_topology_config(session, "/api/v2/feeds/topology")

    assert result == {}


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------

async def test_refresh_tokens_success(settings):
    response = MagicMock()
    response.json = AsyncMock(return_value={"data": {"api_key": "tok-abc"}})
    response.raise_for_status = MagicMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post.return_value = cm

    svc = WebAPI(settings)
    tokens = await svc.refresh_tokens(session)

    assert tokens["TENANT-A"]["connectors"] == "tok-abc"
    assert tokens["TENANT-A"]["sensu"] == "tok-abc"
    assert session.post.call_count == 2


async def test_refresh_tokens_partial_failure(settings):
    # All 3 retry attempts fail for the first component, then the second succeeds.
    # retrying_request retries 3 times, so we need 3 failures + 1 success = 4 calls.
    fail_cm = AsyncMock()
    fail_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("fail"))
    fail_cm.__aexit__ = AsyncMock(return_value=False)

    success_response = MagicMock()
    success_response.json = AsyncMock(return_value={"data": {"api_key": "tok-sensu"}})
    success_response.raise_for_status = MagicMock()
    success_cm = AsyncMock()
    success_cm.__aenter__ = AsyncMock(return_value=success_response)
    success_cm.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    def make_cm(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return fail_cm
        return success_cm

    session = MagicMock()
    session.post.side_effect = make_cm

    svc = WebAPI(settings)
    tokens = await svc.refresh_tokens(session)

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
@patch("argo_automation_cpas.webapi.client_session")
async def test_run_refreshes_and_fetches_config(mock_cs, mock_refresh, mock_save, mock_fetch, settings):
    mock_refresh.return_value = {"TENANT-A": {"connectors": "conn-tok", "sensu": "sensu-tok"}}
    mock_fetch.return_value = {"connector_tenant_topo_type": "GOCDB"}

    session = AsyncMock()
    mock_cs.return_value.__aenter__ = AsyncMock(return_value=session)
    mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

    svc = WebAPI(settings)
    await svc.run()

    mock_refresh.assert_called_once_with(session)
    mock_save.assert_called_once_with(
        {"TENANT-A": {"connectors": "conn-tok", "sensu": "sensu-tok"}},
        settings.webapi.tokens_spool,
    )
    mock_fetch.assert_called_once_with(session, settings.webapi.url_api_config, token="conn-tok")


@patch.object(WebAPI, "fetch_topology_config", new_callable=AsyncMock)
@patch.object(WebAPI, "save_tokens")
@patch.object(WebAPI, "refresh_tokens", new_callable=AsyncMock)
@patch("argo_automation_cpas.webapi.client_session")
async def test_run_no_tokens_skips_save_and_config(mock_cs, mock_refresh, mock_save, mock_fetch, settings):
    mock_refresh.return_value = {"TENANT-A": {}}

    session = AsyncMock()
    mock_cs.return_value.__aenter__ = AsyncMock(return_value=session)
    mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

    svc = WebAPI(settings)
    await svc.run()

    mock_save.assert_not_called()
    mock_fetch.assert_not_called()
