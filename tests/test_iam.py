import time

import pytest
import yaml
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from argo_automation_cpas import iam


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(
        iam=SimpleNamespace(
            api="https://iam.example.com/token",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
            token_spool=str(tmp_path / "iam_access.yml"),
        ),
    )


def _mock_session(status=200, json_data=None):
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data or {})
    response.raise_for_status = MagicMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post.return_value = cm
    return session


# ---------------------------------------------------------------------------
# load_cached_token
# ---------------------------------------------------------------------------

def test_load_cached_token_valid(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "cached-tok", "expires_at": time.time() + 600}, fh)

    assert iam.load_cached_token(settings) == "cached-tok"


def test_load_cached_token_expired(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "old-tok", "expires_at": time.time() - 10}, fh)

    assert iam.load_cached_token(settings) is None


def test_load_cached_token_within_buffer(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "almost-tok", "expires_at": time.time() + 20}, fh)

    assert iam.load_cached_token(settings) is None


def test_load_cached_token_missing_file(settings):
    assert iam.load_cached_token(settings) is None


# ---------------------------------------------------------------------------
# save_token
# ---------------------------------------------------------------------------

def test_save_token(settings):
    iam.save_token(settings, "new-tok", 3600)

    with open(settings.iam.token_spool) as fh:
        data = yaml.safe_load(fh)

    assert data["access_token"] == "new-tok"
    assert data["expires_at"] > time.time()


# ---------------------------------------------------------------------------
# fetch_token
# ---------------------------------------------------------------------------

async def test_fetch_token_success(settings):
    session = _mock_session(json_data={"access_token": "fresh-tok", "expires_in": 1800})

    token = await iam.fetch_token(session, settings)

    assert token == "fresh-tok"
    session.post.assert_called_once_with(
        settings.iam.api,
        data={
            "grant_type": "client_credentials",
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
    )
    # token should have been cached
    with open(settings.iam.token_spool) as fh:
        data = yaml.safe_load(fh)
    assert data["access_token"] == "fresh-tok"


async def test_fetch_token_uses_cache(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "cached-tok", "expires_at": time.time() + 600}, fh)

    session = MagicMock()
    token = await iam.fetch_token(session, settings)

    assert token == "cached-tok"
    session.post.assert_not_called()


async def test_fetch_token_http_error(settings):
    response = MagicMock()
    response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=401
    )

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post.return_value = cm

    token = await iam.fetch_token(session, settings)

    assert token is None


async def test_fetch_token_connection_error(settings):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("unreachable"))
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post.return_value = cm

    token = await iam.fetch_token(session, settings)

    assert token is None
