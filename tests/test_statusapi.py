import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from argo_automation_cpas import statusapi


@pytest.fixture
def settings():
    return SimpleNamespace(
        statusapi=SimpleNamespace(
            api="https://api-status.example.com/v1/automation/tenants/{tenant_id}/status",
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
# report_status
# ---------------------------------------------------------------------------

async def test_report_status_success(settings):
    session = _mock_session("patch")

    await statusapi.report_status(session, settings, "tid-1", "IN_PROGRESS", "bearer-tok")

    session.patch.assert_called_once()
    args, kwargs = session.patch.call_args
    assert "tid-1" in args[0]
    assert kwargs["json"] == {"status": "IN_PROGRESS"}
    assert kwargs["headers"]["Authorization"] == "Bearer bearer-tok"


async def test_report_status_no_token(settings):
    session = _mock_session("patch")

    await statusapi.report_status(session, settings, "tid-1", "DONE", None)

    _, kwargs = session.patch.call_args
    assert "Authorization" not in kwargs["headers"]


async def test_report_status_http_error(settings):
    error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=500)
    session = _mock_session("patch", raise_error=error)

    # should not raise
    await statusapi.report_status(session, settings, "tid-1", "DONE", "tok")


async def test_report_status_connection_error(settings):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("unreachable"))
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.patch.return_value = cm

    await statusapi.report_status(session, settings, "tid-1", "DONE", "tok")


# ---------------------------------------------------------------------------
# fetch_status
# ---------------------------------------------------------------------------

async def test_fetch_status_success(settings, capsys):
    session = _mock_session("get", json_data={"status": "IN_PROGRESS", "tenant_id": "tid-1"})

    await statusapi.fetch_status(session, settings, "tid-1", "bearer-tok")

    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "IN_PROGRESS"


async def test_fetch_status_with_bearer(settings, capsys):
    session = _mock_session("get", json_data={"status": "DONE"})

    await statusapi.fetch_status(session, settings, "tid-1", "my-token")

    _, kwargs = session.get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer my-token"


async def test_fetch_status_no_token(settings, capsys):
    session = _mock_session("get", json_data={"status": "DONE"})

    await statusapi.fetch_status(session, settings, "tid-1", None)

    _, kwargs = session.get.call_args
    assert "Authorization" not in kwargs["headers"]


async def test_fetch_status_http_error(settings, capsys):
    error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=404)
    session = _mock_session("get", raise_error=error)

    await statusapi.fetch_status(session, settings, "tid-1", "tok")

    assert capsys.readouterr().out == ""
