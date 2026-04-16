import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from argo_ams_library.amsexceptions import AmsException, AmsServiceException

from argo_automation_cpas.ams import AMS

from conftest import prime_settings


@pytest.fixture
def settings():
    return prime_settings(SimpleNamespace(
        ams=SimpleNamespace(
            host="api.devel.msg.argo.grnet.gr",
            token="test-token",
            project="TEST-PROJECT",
            subscription="events-sub-1",
            pullmsgs=1,
            ack=False,
            return_immediately=True,
            events=["INIT_TOPOLOGY_CONNECTOR"],
        ),
        automation=SimpleNamespace(
            tenants=[],
        ),
    ))


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.ams.ArgoMessagingService")
def test_init_returns_instance(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.return_value = True
    mock_ams_cls.return_value = mock_ams

    svc = AMS().init()

    mock_ams_cls.assert_called_once_with(
        endpoint=settings.ams.host,
        token=settings.ams.token,
        project=settings.ams.project,
    )
    mock_ams.has_sub.assert_called_once_with(settings.ams.subscription)
    assert svc._ams is mock_ams


@patch("argo_automation_cpas.ams.ArgoMessagingService")
def test_init_service_exception_exits(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.side_effect = AmsServiceException(
        json={"error": {"message": "Unauthorized", "code": 401}, "status": "UNAUTHORIZED"},
        request="has_sub",
    )
    mock_ams_cls.return_value = mock_ams

    with pytest.raises(SystemExit) as exc_info:
        AMS().init()

    assert exc_info.value.code == 1


@patch("argo_automation_cpas.ams.ArgoMessagingService")
def test_init_missing_subscription_exits(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.return_value = False
    mock_ams_cls.return_value = mock_ams

    with pytest.raises(SystemExit) as exc_info:
        AMS().init()

    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# pull_messages
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_messages_success(mock_asyncio, settings):
    msg = MagicMock()
    msg.get_data.return_value = json.dumps({
        "name": "INIT_TOPOLOGY_CONNECTOR",
        "properties": {"tenant_name": "EGI", "tenant_id": "tid-1"},
    })
    mock_asyncio.to_thread = AsyncMock(return_value=[msg])

    svc = AMS()
    svc._ams = MagicMock()

    payloads = await svc.pull_messages()

    assert len(payloads) == 1
    assert payloads[0]["properties"]["tenant_name"] == "EGI"


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_messages_no_messages(mock_asyncio, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=[])

    svc = AMS()
    svc._ams = MagicMock()

    payloads = await svc.pull_messages()

    assert payloads == []


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_messages_ams_exception(mock_asyncio, settings):
    mock_asyncio.to_thread = AsyncMock(side_effect=AmsException("error"))

    svc = AMS()
    svc._ams = MagicMock()

    payloads = await svc.pull_messages()

    assert payloads == []


# ---------------------------------------------------------------------------
# pull_and_print
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_and_print_success(mock_asyncio, settings, capsys):
    msg = MagicMock()
    msg.get_data.return_value = json.dumps({"tenant_name": "EGI"})
    mock_asyncio.to_thread = AsyncMock(return_value=[("ack-1", msg)])

    svc = AMS()
    svc._ams = MagicMock()

    await svc.pull_and_print()

    out = capsys.readouterr().out
    assert '"tenant_name": "EGI"' in out


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_and_print_no_messages(mock_asyncio, settings, capsys):
    mock_asyncio.to_thread = AsyncMock(return_value=[])

    svc = AMS()
    svc._ams = MagicMock()

    await svc.pull_and_print()

    assert "No messages" in capsys.readouterr().out


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_and_print_raw_fallback(mock_asyncio, settings, capsys):
    msg = MagicMock()
    msg.get_data.return_value = "raw-data"
    mock_asyncio.to_thread = AsyncMock(return_value=[("ack-1", msg)])

    svc = AMS()
    svc._ams = MagicMock()

    await svc.pull_and_print()

    assert "raw-data" in capsys.readouterr().out
