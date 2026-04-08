import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import aiohttp

from argo_automation_cpas.http import client_session, retrying_request


# ---------------------------------------------------------------------------
# client_session
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.http.aiohttp.ClientSession")
@patch("argo_automation_cpas.http.aiohttp.TCPConnector")
@patch("argo_automation_cpas.http.aiohttp.ClientTimeout")
def test_client_session_basic(mock_timeout, mock_connector, mock_session):
    settings = SimpleNamespace(request_timeout=30.0, verify_ssl=True)

    client_session(settings)

    mock_timeout.assert_called_once_with(total=30.0)
    mock_connector.assert_called_once_with(ssl=True)
    mock_session.assert_called_once()
    call_kwargs = mock_session.call_args.kwargs
    assert "base_url" not in call_kwargs


@patch("argo_automation_cpas.http.aiohttp.ClientSession")
@patch("argo_automation_cpas.http.aiohttp.TCPConnector")
@patch("argo_automation_cpas.http.aiohttp.ClientTimeout")
def test_client_session_with_base_url(mock_timeout, mock_connector, mock_session):
    settings = SimpleNamespace(request_timeout=10.0, verify_ssl=False)

    client_session(settings, base_url="https://api.example.com")

    mock_connector.assert_called_once_with(ssl=False)
    call_kwargs = mock_session.call_args.kwargs
    assert call_kwargs["base_url"] == "https://api.example.com"


# ---------------------------------------------------------------------------
# retrying_request
# ---------------------------------------------------------------------------

async def test_retrying_request_success():
    response = MagicMock(status=200)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    async with retrying_request(lambda: cm) as resp:
        assert resp.status == 200


@patch("argo_automation_cpas.http.asyncio.sleep", new_callable=AsyncMock)
async def test_retrying_request_retries_on_connection_error(mock_sleep):
    response = MagicMock(status=200)

    fail_cm = AsyncMock()
    fail_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("fail"))
    fail_cm.__aexit__ = AsyncMock(return_value=False)

    ok_cm = AsyncMock()
    ok_cm.__aenter__ = AsyncMock(return_value=response)
    ok_cm.__aexit__ = AsyncMock(return_value=False)

    calls = iter([fail_cm, ok_cm])

    async with retrying_request(lambda: next(calls), retries=3, delay=0.01) as resp:
        assert resp.status == 200

    mock_sleep.assert_called_once()


@patch("argo_automation_cpas.http.asyncio.sleep", new_callable=AsyncMock)
async def test_retrying_request_exhausts_retries(mock_sleep):
    fail_cm = AsyncMock()
    fail_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("fail"))
    fail_cm.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(aiohttp.ClientConnectionError):
        async with retrying_request(lambda: fail_cm, retries=2, delay=0.01):
            pass

    assert mock_sleep.call_count == 1


async def test_retrying_request_does_not_retry_http_errors():
    """HTTP-level errors (ClientResponseError) should NOT be retried."""
    response = MagicMock()
    response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=500
    )

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    async with retrying_request(lambda: cm) as resp:
        with pytest.raises(aiohttp.ClientResponseError):
            resp.raise_for_status()
