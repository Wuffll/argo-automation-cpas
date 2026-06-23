import json
import logging
import os

import aiohttp

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.http import SessionWithRetry

LOG = logging.getLogger(__name__)


class WebAPI:
    def __init__(self):
        self.settings = get_settings()
        self.session = SessionWithRetry(base_url=self.settings.webapi.url)

    async def close(self):
        await self.session.close()

    async def fetch_topology_config(self, url, token=None):
        LOG.info("Fetching topology config from webapi %s", url)
        headers = {"Accept": "application/json"}
        if token:
            headers["x-api-key"] = token
        try:
            body = await self.session.http_get(url, headers=headers)
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

    def load_tokens(self, path):
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError) as exc:
            LOG.warning("Failed to load cached tokens from %s: %s", path, exc)
        return {}

    async def refresh_tokens(self, tenants):
        url_template = self.settings.webapi.url_api_integrations
        headers = {
            "x-api-key": self.settings.webapi.token_component_admin,
            "Accept": "application/json",
        }

        tokens = self.load_tokens(self.settings.webapi.tokens_spool)

        config_filter_tenants = self.settings.automation.tenants

        tenants_array = (
            config_filter_tenants if len(config_filter_tenants) > 0 else tenants
        )

        for tenant_name in tenants_array:
            tokens.setdefault(tenant_name, {})
            for component in self.settings.webapi.components:
                existing = tokens[tenant_name].get(component)
                if existing:
                    LOG.info(
                        "Token already present: component=%s tenant=%s — skipping refresh",
                        component,
                        tenant_name,
                    )
                    continue
                url = url_template.format(component=component, tenant_name=tenant_name)
                LOG.info(
                    "Refreshing token: component=%s tenant=%s url=%s",
                    component,
                    tenant_name,
                    url,
                )
                try:
                    data = await self.session.http_post(url, headers=headers)
                    data = data.get("data", "")
                    token = data.get("api_key", "")
                    tokens[tenant_name][component] = token
                    LOG.info(
                        "Token refreshed: component=%s tenant=%s",
                        component,
                        tenant_name,
                    )
                except aiohttp.ClientError as exc:
                    LOG.warning(
                        "Failed to refresh token for component=%s tenant=%s: %s",
                        component,
                        tenant_name,
                        exc,
                    )
        return tokens

    def save_tokens(self, tokens, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(tokens, fh, indent=2)
        LOG.info("Webapi tokens saved to %s", path)

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

    async def run(self):
        try:
            tokens = await self.refresh_tokens()
            if any(tokens.values()):
                self.save_tokens(tokens, self.settings.webapi.tokens_spool)

            connector_token = self.find_connector_token(tokens)
            if connector_token:
                await self.fetch_topology_config(
                    self.settings.webapi.url_api_config, token=connector_token
                )
        finally:
            await self.close()
