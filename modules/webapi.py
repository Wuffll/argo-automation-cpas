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
            async with SessionWithRetry(base_url=self.settings.webapi.url) as session:
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

        topo_type = entry.get('type', 'none')
        if topo_type.lower() == 'eosc-service-catalog':
            overrides["connector_tenant_topo_type"] = 'PROVIDER'
        elif topo_type.lower() == 'csv':
            overrides["connector_tenant_topo_type"] = 'CSV'

        if "feed_url" in entry:
            overrides["connector_tenant_topo_feed"] = entry["feed_url"]
        if "feed_service_groups" in entry:
            overrides["connector_tenant_topo_feedservicegroups"] = entry["feed_service_groups"]
        if "feed_service_endpoints" in entry:
            overrides["connector_tenant_topo_feedserviceendpoints"] = entry["feed_service_endpoints"]
        if "feed_service_endpoints_extensions" in entry:
            overrides["connector_tenant_topo_feedserviceendpointsext"] = entry["feed_service_endpoints_extensions"]

        if topo_type.lower() == 'csv':
            LOG.info(
                "Topology config: topo_type=%s topo_feed=%s",
                overrides.get("connector_tenant_topo_type", "n/a"),
                overrides.get("connector_tenant_topo_feed", "n/a"),
            )
        elif topo_type.lower() == 'eosc-service-catalog':
            LOG.info(
                "Topology config: topo_type=%s topo_feed_servicegroups=%s topo_feed_service_endpoints=%s topo_feed_service_endpoints_ext=%s",
                overrides.get("connector_tenant_topo_type", "n/a"),
                overrides.get("connector_tenant_topo_feedservicegroups", "n/a"),
                overrides.get("connector_tenant_topo_feedserviceendpoints", "n/a"),
                overrides.get("connector_tenant_topo_feedserviceendpointsext", "n/a"),
            )
        return overrides

    def find_connector_token(self, component_tokens, tenant_name):
        if not tenant_name:
            return None

        for name, tokens in (component_tokens or {}).items():
            if str(name).upper() != tenant_name.upper():
                continue
            for component, token in (tokens or {}).items():
                if "connector" in component and token:
                    return token
        return None

    async def run(self, allowed_tenants=[]):
        tokens = await self.tokens.refresh_tokens(allowed_tenants)
        if any(tokens.values()):
            self.tokens.save_tokens(tokens, self.settings.webapi.tokens_spool)

        connector_token = None
        for tenant_name in tokens or {}:
            connector_token = self.find_connector_token(tokens, tenant_name)
            if connector_token:
                break
        if connector_token:
            await self.fetch_topology_config(
                self.settings.webapi.url_api_config, token=connector_token
            )
