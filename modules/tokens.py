import aiohttp
import json
import logging
import os

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.http import SessionWithRetry

LOG = logging.getLogger(__name__)


class Tokens:
    def __init__(self):
        self.settings = get_settings()
        self.session = SessionWithRetry(base_url=self.settings.ams.url)

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

    async def refresh_tokens(self, tenants_array):
        url_template = self.settings.ams.url_api_integrations

        headers = {
            "x-api-key": self.settings.ams.token_component_admin,
            "Accept": "application/json",
        }

        tokens = self.load_tokens(self.settings.ams.tokens_spool)

        for tenant_name in tenants_array:
            tokens.setdefault(tenant_name, {})
            for component in self.settings.ams.components:
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
        LOG.info("AMS tokens saved to %s", path)

    async def close(self):
        await self.session.close()
