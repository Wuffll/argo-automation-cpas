import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from argo_ams_library.amsexceptions import AmsException

from argo_automation_cpas import ams


@pytest.fixture
def settings():
    return SimpleNamespace(
        ams=SimpleNamespace(subscription="events-sub-1"),
    )


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
