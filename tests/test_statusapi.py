import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from argo_automation_cpas.statusapi import StatusAPI

from conftest import prime_settings


@pytest.fixture
def settings():
    return prime_settings(SimpleNamespace(
        request_timeout=30.0,
        verify_ssl=True,
        statusapi=SimpleNamespace(
            api="https://api-status.example.com/v1/automation/tenants/{tenant_id}/status",
        ),
    ))


@pytest.fixture
def svc(settings):
    with patch("argo_automation_cpas.statusapi.SessionWithRetry"):
        s = StatusAPI()
    s.session = MagicMock(
        http_get=AsyncMock(),
        http_patch=AsyncMock(),
        close=AsyncMock(),
    )
    return s


# ---------------------------------------------------------------------------
# report_status
# ---------------------------------------------------------------------------

async def test_report_status_success(svc):
    await svc.report_status("tid-1", "IN_PROGRESS", "bearer-tok")

    svc.session.http_patch.assert_called_once()
    call_args = svc.session.http_patch.call_args
    assert "tid-1" in call_args.args[0]
    assert call_args.kwargs["json"] == {"status": "IN_PROGRESS"}
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer bearer-tok"


async def test_report_status_no_token(svc):
    await svc.report_status("tid-1", "DONE", None)

    call_args = svc.session.http_patch.call_args
    assert "Authorization" not in call_args.kwargs["headers"]


async def test_report_status_http_error(svc):
    svc.session.http_patch.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=500
    )
    await svc.report_status("tid-1", "DONE", "tok")


async def test_report_status_connection_error(svc):
    svc.session.http_patch.side_effect = aiohttp.ClientConnectionError("unreachable")
    await svc.report_status("tid-1", "DONE", "tok")


# ---------------------------------------------------------------------------
# fetch_status
# ---------------------------------------------------------------------------

async def test_fetch_status_success(svc, capsys):
    svc.session.http_get.return_value = {"status": "IN_PROGRESS", "tenant_id": "tid-1"}

    await svc.fetch_status("tid-1", "bearer-tok")

    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "IN_PROGRESS"


async def test_fetch_status_with_bearer(svc, capsys):
    svc.session.http_get.return_value = {"status": "DONE"}

    await svc.fetch_status("tid-1", "my-token")

    call_args = svc.session.http_get.call_args
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer my-token"


async def test_fetch_status_no_token(svc, capsys):
    svc.session.http_get.return_value = {"status": "DONE"}

    await svc.fetch_status("tid-1", None)

    call_args = svc.session.http_get.call_args
    assert "Authorization" not in call_args.kwargs["headers"]


async def test_fetch_status_http_error(svc, capsys):
    svc.session.http_get.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=404
    )

    await svc.fetch_status("tid-1", "tok")

    assert capsys.readouterr().out == ""
