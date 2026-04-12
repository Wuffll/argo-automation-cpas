import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from argo_automation_cpas.statusapi import StatusAPI


@pytest.fixture
def settings():
    return SimpleNamespace(
        statusapi=SimpleNamespace(
            api="https://api-status.example.com/v1/automation/tenants/{tenant_id}/status",
        ),
    )


def _mock_session(return_value=None, side_effect=None):
    return MagicMock(
        http_get=AsyncMock(return_value=return_value, side_effect=side_effect),
        http_post=AsyncMock(return_value=return_value, side_effect=side_effect),
        http_patch=AsyncMock(return_value=return_value, side_effect=side_effect),
    )


# ---------------------------------------------------------------------------
# report_status
# ---------------------------------------------------------------------------

async def test_report_status_success(settings):
    session = _mock_session()

    svc = StatusAPI(settings)
    await svc.report_status(session, "tid-1", "IN_PROGRESS", "bearer-tok")

    session.http_patch.assert_called_once()
    call_kwargs = session.http_patch.call_args
    assert "tid-1" in call_kwargs.args[0]
    assert call_kwargs.kwargs["json"] == {"status": "IN_PROGRESS"}
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer bearer-tok"


async def test_report_status_no_token(settings):
    session = _mock_session()

    svc = StatusAPI(settings)
    await svc.report_status(session, "tid-1", "DONE", None)

    call_kwargs = session.http_patch.call_args
    assert "Authorization" not in call_kwargs.kwargs["headers"]


async def test_report_status_http_error(settings):
    error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=500)
    session = _mock_session(side_effect=error)

    svc = StatusAPI(settings)
    await svc.report_status(session, "tid-1", "DONE", "tok")


async def test_report_status_connection_error(settings):
    session = _mock_session(side_effect=aiohttp.ClientConnectionError("unreachable"))

    svc = StatusAPI(settings)
    await svc.report_status(session, "tid-1", "DONE", "tok")


# ---------------------------------------------------------------------------
# fetch_status
# ---------------------------------------------------------------------------

async def test_fetch_status_success(settings, capsys):
    session = _mock_session(return_value={"status": "IN_PROGRESS", "tenant_id": "tid-1"})

    svc = StatusAPI(settings)
    await svc.fetch_status(session, "tid-1", "bearer-tok")

    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "IN_PROGRESS"


async def test_fetch_status_with_bearer(settings, capsys):
    session = _mock_session(return_value={"status": "DONE"})

    svc = StatusAPI(settings)
    await svc.fetch_status(session, "tid-1", "my-token")

    call_kwargs = session.http_get.call_args
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer my-token"


async def test_fetch_status_no_token(settings, capsys):
    session = _mock_session(return_value={"status": "DONE"})

    svc = StatusAPI(settings)
    await svc.fetch_status(session, "tid-1", None)

    call_kwargs = session.http_get.call_args
    assert "Authorization" not in call_kwargs.kwargs["headers"]


async def test_fetch_status_http_error(settings, capsys):
    error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=404)
    session = _mock_session(side_effect=error)

    svc = StatusAPI(settings)
    await svc.fetch_status(session, "tid-1", "tok")

    assert capsys.readouterr().out == ""
