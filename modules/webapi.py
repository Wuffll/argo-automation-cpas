import json
import logging
import os

import aiohttp

from argo_automation_cpas.http import client_session, retrying_request

LOG = logging.getLogger(__name__)


async def probe(session, url):
    LOG.info("Probing Web API endpoint %s", url)
    try:
        async with retrying_request(lambda: session.get("/")) as response:
            LOG.info("Received probe status %s", response.status)
    except aiohttp.ClientError as exc:
        LOG.warning("Web API probe failed: %s", exc)


async def fetch_topology_config(session, url, token=None):
    LOG.info("Fetching topology config from webapi %s", url)
    headers = {"Accept": "application/json"}
    if token:
        headers["x-api-key"] = token
    try:
        async with retrying_request(lambda: session.get(url, headers=headers)) as response:
            response.raise_for_status()
            body = await response.json()
    except aiohttp.ClientError as exc:
        LOG.warning("Failed to fetch topology config from webapi: %s", exc)
        return {}

    data = body.get("data", [])
    if not data:
        LOG.warning("Empty data in topology config response")
        return {}

    entry = data[0]
    overrides = {}
    if "type" in entry:
        overrides["connector_tenant_topo_type"] = entry["type"]
    if "feed_url" in entry:
        overrides["connector_tenant_topo_feed"] = entry["feed_url"]

    LOG.info(
        "Topology config: topo_type=%s topo_feed=%s",
        overrides.get("connector_tenant_topo_type", "n/a"),
        overrides.get("connector_tenant_topo_feed", "n/a"),
    )
    return overrides


async def refresh_tokens(session, settings):
    url_template = settings.webapi.url_api_integrations
    headers = {
        "x-api-key": settings.webapi.token_component_admin,
        "Accept": "application/json",
    }

    tokens = {}
    for tenant_name in settings.automation.tenants:
        tokens[tenant_name] = {}
        for component in settings.webapi.components:
            url = url_template.format(component=component, tenant_name=tenant_name)
            LOG.info("Refreshing token: component=%s tenant=%s url=%s", component, tenant_name, url)
            try:
                async with retrying_request(lambda u=url, h=headers: session.post(u, headers=h)) as response:
                    response.raise_for_status()
                    data = await response.json()
                    data = data.get("data", "")
                    token = data.get("api_key", "")
                    tokens[tenant_name][component] = token
                    LOG.info("Token refreshed: component=%s tenant=%s", component, tenant_name)
            except aiohttp.ClientError as exc:
                LOG.warning("Failed to refresh token for component=%s tenant=%s: %s",
                            component, tenant_name, exc)
    return tokens


def save_tokens(tokens, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(tokens, fh, indent=2)
    LOG.info("Webapi tokens saved to %s", path)


def find_connector_token(tokens):
    return next(
        (t[component] for t in tokens.values() for component in t if "connector" in component),
        None,
    )


async def run(settings):
    async with client_session(settings, base_url=settings.webapi.url) as session:
        tokens = await refresh_tokens(session, settings)
        if any(tokens.values()):
            save_tokens(tokens, settings.webapi.tokens_spool)

        connector_token = find_connector_token(tokens)
        if connector_token:
            await fetch_topology_config(session, settings.webapi.url_api_config, token=connector_token)
