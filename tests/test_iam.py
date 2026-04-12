import time

import pytest
import yaml
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from argo_automation_cpas.iam import IAM


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(
        request_timeout=30.0,
        verify_ssl=True,
        iam=SimpleNamespace(
            api="https://iam.example.com/token",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
            token_spool=str(tmp_path / "iam_access.yml"),
        ),
    )


@pytest.fixture
def svc(settings):
    with patch("argo_automation_cpas.iam.SessionWithRetry"):
        s = IAM(settings)
    s.session = MagicMock(
        http_post=AsyncMock(),
        close=AsyncMock(),
    )
    return s


# ---------------------------------------------------------------------------
# load_cached_token
# ---------------------------------------------------------------------------

def test_load_cached_token_valid(svc):
    with open(svc.settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "cached-tok", "expires_at": time.time() + 600}, fh)

    assert svc.load_cached_token() == "cached-tok"


def test_load_cached_token_expired(svc):
    with open(svc.settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "old-tok", "expires_at": time.time() - 10}, fh)

    assert svc.load_cached_token() is None


def test_load_cached_token_within_buffer(svc):
    with open(svc.settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "almost-tok", "expires_at": time.time() + 20}, fh)

    assert svc.load_cached_token() is None


def test_load_cached_token_missing_file(svc):
    assert svc.load_cached_token() is None


# ---------------------------------------------------------------------------
# save_token
# ---------------------------------------------------------------------------

def test_save_token(svc):
    svc.save_token("new-tok", 3600)

    with open(svc.settings.iam.token_spool) as fh:
        data = yaml.safe_load(fh)

    assert data["access_token"] == "new-tok"
    assert data["expires_at"] > time.time()


# ---------------------------------------------------------------------------
# fetch_token
# ---------------------------------------------------------------------------

async def test_fetch_token_success(svc):
    svc.session.http_post.return_value = {"access_token": "fresh-tok", "expires_in": 1800}

    token = await svc.fetch_token()

    assert token == "fresh-tok"
    svc.session.http_post.assert_called_once_with(
        svc.settings.iam.api,
        data={
            "grant_type": "client_credentials",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scope": "openid entitlements",
        },
    )
    with open(svc.settings.iam.token_spool) as fh:
        data = yaml.safe_load(fh)
    assert data["access_token"] == "fresh-tok"


async def test_fetch_token_uses_cache(svc):
    with open(svc.settings.iam.token_spool, "w") as fh:
        yaml.dump({"access_token": "cached-tok", "expires_at": time.time() + 600}, fh)

    token = await svc.fetch_token()

    assert token == "cached-tok"
    svc.session.http_post.assert_not_called()


async def test_fetch_token_http_error(svc):
    svc.session.http_post.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=401
    )

    token = await svc.fetch_token()

    assert token is None


async def test_fetch_token_connection_error(svc):
    svc.session.http_post.side_effect = aiohttp.ClientConnectionError("unreachable")

    token = await svc.fetch_token()

    assert token is None
