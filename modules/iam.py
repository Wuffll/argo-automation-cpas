import logging
import os
import time

import aiohttp
import yaml

from argo_automation_cpas.http import retrying_request

LOG = logging.getLogger(__name__)


def load_cached_token(settings):
    path = settings.iam.token_spool
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        token = data.get("access_token", "")
        expires_at = float(data.get("expires_at", 0))
        if token and time.time() < expires_at - 30:
            LOG.info("Using cached IAM token from %s (expires in %.0fs)", path, expires_at - time.time())
            return token
    except (OSError, ValueError):
        pass
    return None


def save_token(settings, token, expires_in):
    path = settings.iam.token_spool
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        yaml.dump({"access_token": token, "expires_at": time.time() + expires_in}, fh)
    LOG.info("IAM token saved to %s", path)


async def fetch_token(session, settings):
    cached = load_cached_token(settings)
    if cached:
        return cached

    LOG.info("Fetching OIDC token from IAM %s", settings.iam.api)

    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.iam.oidc_client_id,
        "client_secret": settings.iam.oidc_client_secret,
        "scope": "openid entitlements",
    }

    try:
        async with retrying_request(lambda: session.post(settings.iam.api, data=payload)) as response:
            response.raise_for_status()
            data = await response.json()
            token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            LOG.info("IAM token obtained (expires_in=%s)", expires_in)
            save_token(settings, token, expires_in)
            return token
    except aiohttp.ClientError as exc:
        LOG.warning("IAM token request failed: %s", exc)
        return None
