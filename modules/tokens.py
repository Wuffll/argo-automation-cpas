import aiohttp
import json
import logging
import os

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.http import SessionWithRetry

from typing import Literal

TokenTypes = Literal["ams", "webapi"]

LOG = logging.getLogger(__name__)


class ComponentTokens:
    def __init__(self, type_tok: TokenTypes):
        self.target_settings = getattr(get_settings(), type_tok.lower())
        self.type_tok = type_tok
        self.any_refresh = False

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
        url_template = self.target_settings.url_api_integrations

        headers = {
            "x-api-key": self.target_settings.token_component_admin,
            "Accept": "application/json",
        }

        tokens = self.load_tokens(self.target_settings.tokens_spool)

        for tenant_name in tenants_array:
            tokens.setdefault(tenant_name, {})
            for component in self.target_settings.components:
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
                    async with SessionWithRetry(base_url=self.target_settings.url) as session:
                        data = await session.http_post(url, headers=headers)
                        data = data.get("data", "")
                        token = data.get("api_key", "")
                        self.any_refresh = True
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
        if self.any_refresh:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                json.dump(tokens, fh, indent=2)
            LOG.info(f"{self.type_tok.upper()} tokens saved to %s", path)
