import pytest
import aiohttp
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from argo_automation_cpas.app import Application


@pytest.fixture
def settings():
    return SimpleNamespace(
        request_timeout=30.0,
        verify_ssl=True,
        ansible_private_data_dir="ansible",
        ansible_playbook="init.yml",
        general=SimpleNamespace(
            ssh_private_key="/home/user/.ssh/sshkey",
        ),
        webapi=SimpleNamespace(
            host="api.devel.mon.argo.grnet.gr",
            url="https://api.devel.mon.argo.grnet.gr",
        ),
        iam=SimpleNamespace(
            host="https://login-devel.einfra.grnet.gr/auth/realms/einfra/protocol/openid-connect/token",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
        ),
        ams=SimpleNamespace(
            host="api.devel.msg.argo.grnet.gr",
            token="test-token",
            project="TEST-PROJECT",
            subscription="events-sub-1",
        ),
    )


def _mock_session(method, status=200, json_data=None, raise_on_raise_for_status=None):
    """Return a session mock where session.<method>() acts as an async context manager."""
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data or {})

    if raise_on_raise_for_status:
        response.raise_for_status = MagicMock(side_effect=raise_on_raise_for_status)
    else:
        response.raise_for_status = MagicMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    getattr(session, method).return_value = cm

    return session


# ---------------------------------------------------------------------------
# _probe_webapi
# ---------------------------------------------------------------------------

async def test_probe_webapi_success(settings):
    app = Application(settings)
    session = _mock_session("get", status=200)

    await app._probe_webapi(session)

    session.get.assert_called_once_with("/")


async def test_probe_webapi_client_error(settings):
    app = Application(settings)

    response_cm = AsyncMock()
    response_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("unreachable"))
    response_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get.return_value = response_cm

    # Should not raise — errors are logged and swallowed
    await app._probe_webapi(session)


# ---------------------------------------------------------------------------
# _fetch_iam_token
# ---------------------------------------------------------------------------

async def test_fetch_iam_token_success(settings):
    app = Application(settings)
    session = _mock_session(
        "post",
        status=200,
        json_data={"access_token": "my-token", "expires_in": 3600},
    )

    token = await app._fetch_iam_token(session)

    assert token == "my-token"
    session.post.assert_called_once_with(
        settings.iam.host,
        data={
            "grant_type": "client_credentials",
            "client_id": settings.iam.oidc_client_id,
            "client_secret": settings.iam.oidc_client_secret,
        },
    )


async def test_fetch_iam_token_http_error(settings):
    app = Application(settings)

    error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=401)
    session = _mock_session("post", status=401, raise_on_raise_for_status=error)

    token = await app._fetch_iam_token(session)

    assert token is None


async def test_fetch_iam_token_connection_error(settings):
    app = Application(settings)

    response_cm = AsyncMock()
    response_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("unreachable"))
    response_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post.return_value = response_cm

    token = await app._fetch_iam_token(session)

    assert token is None


# ---------------------------------------------------------------------------
# run (integration of all pieces)
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.ansible_runner.run")
@patch("argo_automation_cpas.app.asyncio.to_thread")
@patch("argo_automation_cpas.app.aiohttp.TCPConnector")
@patch("argo_automation_cpas.app.aiohttp.ClientSession")
async def test_run_calls_all_services(
    mock_session_cls, mock_connector_cls, mock_to_thread, mock_ansible_run, settings
):
    mock_ams = MagicMock()
    mock_to_thread.return_value = mock_ams

    # Build a fake session that works as async context manager
    webapi_response = MagicMock()
    webapi_response.status = 200
    webapi_cm = AsyncMock()
    webapi_cm.__aenter__ = AsyncMock(return_value=webapi_response)
    webapi_cm.__aexit__ = AsyncMock(return_value=False)

    iam_response = MagicMock()
    iam_response.status = 200
    iam_response.json = AsyncMock(return_value={"access_token": "tok", "expires_in": 3600})
    iam_response.raise_for_status = MagicMock()
    iam_cm = AsyncMock()
    iam_cm.__aenter__ = AsyncMock(return_value=iam_response)
    iam_cm.__aexit__ = AsyncMock(return_value=False)

    webapi_session = MagicMock()
    webapi_session.get.return_value = webapi_cm
    webapi_session.__aenter__ = AsyncMock(return_value=webapi_session)
    webapi_session.__aexit__ = AsyncMock(return_value=False)

    iam_session = MagicMock()
    iam_session.post.return_value = iam_cm
    iam_session.__aenter__ = AsyncMock(return_value=iam_session)
    iam_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_cls.side_effect = [webapi_session, iam_session]
    mock_connector_cls.return_value = MagicMock()

    mock_runner = MagicMock(status="successful", rc=0)
    mock_ansible_run.return_value = mock_runner

    app = Application(settings)
    await app.run()

    assert mock_to_thread.called
    webapi_session.get.assert_called_once_with("/")
    iam_session.post.assert_called_once()
