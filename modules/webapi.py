import logging
import aiohttp

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.tokens import ComponentTokens
from argo_automation_cpas.http import SessionWithRetry

LOG = logging.getLogger(__name__)


class WebAPI:
    def __init__(self):
        self.settings = get_settings()
        self.tokens = ComponentTokens("webapi")

    async def fetch_topology_config(self, url, token=None):
        LOG.info("Fetching topology config from webapi %s", url)
        headers = {"Accept": "application/json"}
        if token:
            headers["x-api-key"] = token
        try:
            async with SessionWithRetry() as session:
                body = await session.http_get(url, headers=headers)
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

    def find_connector_token(self, tokens):
        return next(
            (
                t[component]
                for t in tokens.values()
                for component in t
                if "connector" in component
            ),
            None,
        )

    async def run(self, allowed_tenants=[]):
        tokens = await self.tokens.refresh_tokens(allowed_tenants)
        if any(tokens.values()):
            self.tokens.save_tokens(tokens, self.settings.webapi.tokens_spool)

        connector_token = self.find_connector_token(tokens)
        if connector_token:
            await self.fetch_topology_config(
                self.settings.webapi.url_api_config, token=connector_token
            )
