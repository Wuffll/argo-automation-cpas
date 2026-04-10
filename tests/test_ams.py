import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from argo_ams_library.amsexceptions import AmsException, AmsServiceException

from argo_automation_cpas import ams


@pytest.fixture
def settings():
    return SimpleNamespace(
        ams=SimpleNamespace(
            host="api.devel.msg.argo.grnet.gr",
            token="test-token",
            project="TEST-PROJECT",
            subscription="events-sub-1",
            pullmsgs=1,
        ),
    )


# ---------------------------------------------------------------------------
# init_ams
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.ams.ArgoMessagingService")
def test_init_ams_returns_instance(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.return_value = True
    mock_ams_cls.return_value = mock_ams

    result = ams.init_ams(settings)

    mock_ams_cls.assert_called_once_with(
        endpoint=settings.ams.host,
        token=settings.ams.token,
        project=settings.ams.project,
    )
    mock_ams.has_sub.assert_called_once_with(settings.ams.subscription)
    assert result is mock_ams


@patch("argo_automation_cpas.ams.ArgoMessagingService")
def test_init_ams_service_exception_exits(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.side_effect = AmsServiceException(
        json={"error": "Unauthorized", "status_code": 401, "status": "UNAUTHORIZED"}
    )
    mock_ams_cls.return_value = mock_ams

    with pytest.raises(SystemExit) as exc_info:
        ams.init_ams(settings)

    assert exc_info.value.code == 1


@patch("argo_automation_cpas.ams.ArgoMessagingService")
def test_init_ams_missing_subscription_exits(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.return_value = False
    mock_ams_cls.return_value = mock_ams

    with pytest.raises(SystemExit) as exc_info:
        ams.init_ams(settings)

    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# pull_message
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_message_success(mock_asyncio, settings):
    msg = MagicMock()
    msg.get_data.return_value = json.dumps({"tenant_name": "EGI", "tenant_id": "tid-1"})
    mock_asyncio.to_thread = AsyncMock(return_value=[msg])

    payload = await ams.pull_message(MagicMock(), settings)

    assert payload == {"tenant_name": "EGI", "tenant_id": "tid-1"}


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_message_no_messages(mock_asyncio, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=[])

    payload = await ams.pull_message(MagicMock(), settings)

    assert payload is None


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_message_ams_exception(mock_asyncio, settings):
    mock_asyncio.to_thread = AsyncMock(side_effect=AmsException("error"))

    payload = await ams.pull_message(MagicMock(), settings)

    assert payload is None


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_message_invalid_json(mock_asyncio, settings):
    msg = MagicMock()
    msg.get_data.return_value = "not-json"
    mock_asyncio.to_thread = AsyncMock(return_value=[msg])

    payload = await ams.pull_message(MagicMock(), settings)

    assert payload is None


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_message_missing_fields(mock_asyncio, settings):
    msg = MagicMock()
    msg.get_data.return_value = json.dumps({"tenant_name": "EGI"})
    mock_asyncio.to_thread = AsyncMock(return_value=[msg])

    payload = await ams.pull_message(MagicMock(), settings)

    assert payload is None


# ---------------------------------------------------------------------------
# pull_and_print
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_and_print_success(mock_asyncio, settings, capsys):
    msg = MagicMock()
    msg.get_data.return_value = json.dumps({"tenant_name": "EGI"})
    mock_asyncio.to_thread = AsyncMock(return_value=[("ack-1", msg)])

    await ams.pull_and_print(MagicMock(), settings)

    out = capsys.readouterr().out
    assert '"tenant_name": "EGI"' in out


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_and_print_no_messages(mock_asyncio, settings, capsys):
    mock_asyncio.to_thread = AsyncMock(return_value=[])

    await ams.pull_and_print(MagicMock(), settings)

    assert "No messages" in capsys.readouterr().out


@patch("argo_automation_cpas.ams.asyncio")
async def test_pull_and_print_raw_fallback(mock_asyncio, settings, capsys):
    msg = MagicMock()
    msg.get_data.return_value = "raw-data"
    mock_asyncio.to_thread = AsyncMock(return_value=[("ack-1", msg)])

    await ams.pull_and_print(MagicMock(), settings)

    assert "raw-data" in capsys.readouterr().out
