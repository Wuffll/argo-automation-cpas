import time

import pytest
import yaml
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from argo_automation_cpas.iam import IAM


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


def _mock_session(return_value=None, side_effect=None):
    session = MagicMock()
    session.http_post = AsyncMock(return_value=return_value, side_effect=side_effect)
    return session


# ---------------------------------------------------------------------------
# load_cached_token
# ---------------------------------------------------------------------------

def test_load_cached_token_valid(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "cached-tok", "expires_at": time.time() + 600}, fh)

    assert IAM(settings).load_cached_token() == "cached-tok"


def test_load_cached_token_expired(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "old-tok", "expires_at": time.time() - 10}, fh)

    assert IAM(settings).load_cached_token() is None


def test_load_cached_token_within_buffer(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "almost-tok", "expires_at": time.time() + 20}, fh)

    assert IAM(settings).load_cached_token() is None


def test_load_cached_token_missing_file(settings):
    assert IAM(settings).load_cached_token() is None


# ---------------------------------------------------------------------------
# save_token
# ---------------------------------------------------------------------------

def test_save_token(settings):
    IAM(settings).save_token("new-tok", 3600)

    with open(settings.iam.token_spool) as fh:
        data = yaml.safe_load(fh)

    assert data["access_token"] == "new-tok"
    assert data["expires_at"] > time.time()


# ---------------------------------------------------------------------------
# fetch_token
# ---------------------------------------------------------------------------

async def test_fetch_token_success(settings):
    session = _mock_session(return_value={"access_token": "fresh-tok", "expires_in": 1800})

    token = await IAM(settings).fetch_token(session)

    assert token == "fresh-tok"
    session.http_post.assert_called_once_with(
        settings.iam.api,
        data={
            "grant_type": "client_credentials",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scope": "openid entitlements",
        },
    )
    with open(settings.iam.token_spool) as fh:
        data = yaml.safe_load(fh)
    assert data["access_token"] == "fresh-tok"


async def test_fetch_token_uses_cache(settings):
    with open(settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "cached-tok", "expires_at": time.time() + 600}, fh)

    session = MagicMock()
    token = await IAM(settings).fetch_token(session)

    assert token == "cached-tok"


async def test_fetch_token_http_error(settings):
    session = _mock_session(
        side_effect=aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=401
        )
    )

    token = await IAM(settings).fetch_token(session)

    assert token is None


async def test_fetch_token_connection_error(settings):
    session = _mock_session(side_effect=aiohttp.ClientConnectionError("unreachable"))

    token = await IAM(settings).fetch_token(session)

    assert token is None
