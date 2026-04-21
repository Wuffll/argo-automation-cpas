import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import aiohttp

from argo_automation_cpas.http import SessionWithRetry

from conftest import prime_settings


@pytest.fixture
def settings():
    return prime_settings(SimpleNamespace(general=SimpleNamespace(
        request_timeout=30.0, verify_ssl=True, retries=3, retry_delay=1.0,
    )))


# ---------------------------------------------------------------------------
# SessionWithRetry — init / context manager
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.http.aiohttp.ClientSession")
@patch("argo_automation_cpas.http.aiohttp.TCPConnector")
@patch("argo_automation_cpas.http.aiohttp.ClientTimeout")
def test_session_init_basic(mock_timeout, mock_connector, mock_session, settings):
    svc = SessionWithRetry()

    mock_timeout.assert_called_once_with(total=30.0)
    mock_connector.assert_called_once_with(ssl=True)
    mock_session.assert_called_once()
    call_kwargs = mock_session.call_args.kwargs
    assert "base_url" not in call_kwargs


@patch("argo_automation_cpas.http.aiohttp.ClientSession")
@patch("argo_automation_cpas.http.aiohttp.TCPConnector")
@patch("argo_automation_cpas.http.aiohttp.ClientTimeout")
def test_session_init_with_base_url(mock_timeout, mock_connector, mock_session):
    prime_settings(SimpleNamespace(general=SimpleNamespace(
        request_timeout=10.0, verify_ssl=False, retries=3, retry_delay=1.0,
    )))

    SessionWithRetry(base_url="https://api.example.com")

    mock_connector.assert_called_once_with(ssl=False)
    call_kwargs = mock_session.call_args.kwargs
    assert call_kwargs["base_url"] == "https://api.example.com"


# ---------------------------------------------------------------------------
# http_get
# ---------------------------------------------------------------------------

async def test_http_get_success(settings):
    response = MagicMock(status=200, content_type="application/json")
    response.json = AsyncMock(return_value={"key": "value"})
    response.raise_for_status = MagicMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    svc = SessionWithRetry()
    svc.session = MagicMock()
    svc.session.get = MagicMock(return_value=cm)

    result = await svc.http_get("https://example.com/api")

    assert result == {"key": "value"}


async def test_http_get_text_response(settings):
    response = MagicMock(status=200, content_type="text/plain")
    response.text = AsyncMock(return_value="OK")
    response.raise_for_status = MagicMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    svc = SessionWithRetry()
    svc.session = MagicMock()
    svc.session.get = MagicMock(return_value=cm)

    result = await svc.http_get("https://example.com/healthz")

    assert result == "OK"


# ---------------------------------------------------------------------------
# http_post
# ---------------------------------------------------------------------------

async def test_http_post_success(settings):
    response = MagicMock(status=200, content_type="application/json")
    response.json = AsyncMock(return_value={"token": "abc"})
    response.raise_for_status = MagicMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    svc = SessionWithRetry()
    svc.session = MagicMock()
    svc.session.post = MagicMock(return_value=cm)

    result = await svc.http_post("https://example.com/token", data={"grant": "cc"})

    assert result == {"token": "abc"}
    call_kwargs = svc.session.post.call_args.kwargs
    assert call_kwargs["data"] == {"grant": "cc"}


# ---------------------------------------------------------------------------
# http_patch
# ---------------------------------------------------------------------------

async def test_http_patch_success(settings):
    response = MagicMock(status=200, content_type="application/json")
    response.json = AsyncMock(return_value={"status": "ok"})
    response.raise_for_status = MagicMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    svc = SessionWithRetry()
    svc.session = MagicMock()
    svc.session.patch = MagicMock(return_value=cm)

    result = await svc.http_patch("https://example.com/status", json={"status": "DONE"})

    assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.http.asyncio.sleep", new_callable=AsyncMock)
async def test_retries_on_connection_error(mock_sleep, settings):
    response = MagicMock(status=200, content_type="application/json")
    response.json = AsyncMock(return_value={"ok": True})
    response.raise_for_status = MagicMock()

    fail_cm = MagicMock()
    fail_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("fail"))
    fail_cm.__aexit__ = AsyncMock(return_value=False)

    ok_cm = MagicMock()
    ok_cm.__aenter__ = AsyncMock(return_value=response)
    ok_cm.__aexit__ = AsyncMock(return_value=False)

    calls = iter([fail_cm, ok_cm])

    svc = SessionWithRetry()
    svc.retry_delay = 0.01
    svc.session = MagicMock()
    svc.session.get = MagicMock(side_effect=lambda *a, **kw: next(calls))

    result = await svc.http_get("https://example.com/api")

    assert result == {"ok": True}
    mock_sleep.assert_called_once()


@patch("argo_automation_cpas.http.asyncio.sleep", new_callable=AsyncMock)
async def test_exhausts_retries(mock_sleep, settings):
    fail_cm = MagicMock()
    fail_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("fail"))
    fail_cm.__aexit__ = AsyncMock(return_value=False)

    svc = SessionWithRetry()
    svc.retries = 2
    svc.retry_delay = 0.01
    svc.session = MagicMock()
    svc.session.get = MagicMock(return_value=fail_cm)

    with pytest.raises(aiohttp.ClientConnectionError):
        await svc.http_get("https://example.com/api")

    assert mock_sleep.call_count == 1


async def test_does_not_retry_http_errors(settings):
    response = MagicMock()
    response.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=500
        )
    )

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    svc = SessionWithRetry()
    svc.session = MagicMock()
    svc.session.get = MagicMock(return_value=cm)

    with pytest.raises(aiohttp.ClientResponseError):
        await svc.http_get("https://example.com/missing")

    assert svc.session.get.call_count == 1
