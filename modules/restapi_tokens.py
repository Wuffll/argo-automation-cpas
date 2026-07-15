import json
import logging
import os
import secrets
import string

from argo_automation_cpas.config import get_settings

LOG = logging.getLogger(__name__)

RESTAPI_TOKEN_LENGTH = 32
RESTAPI_TOKEN_ALPHABET = string.ascii_letters + string.digits


class RestAPITokens:
    def __init__(self):
        self.settings = get_settings()
        self.token_spool = self.settings.ansible.poem_restapi_token

    def generate_token(self, length=RESTAPI_TOKEN_LENGTH):
        return "".join(secrets.choice(RESTAPI_TOKEN_ALPHABET) for _ in range(length))

    def load_tokens(self):
        if not os.path.exists(self.token_spool):
            return {}
        try:
            with open(self.token_spool) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
            LOG.warning("REST-API token spool is not a mapping: %s", self.token_spool)
        except (OSError, json.JSONDecodeError) as exc:
            LOG.warning("Failed to load REST-API tokens from %s: %s", self.token_spool, exc)
        return {}

    def save_tokens(self, tokens):
        os.makedirs(os.path.dirname(self.token_spool), exist_ok=True)
        with open(self.token_spool, "w") as fh:
            json.dump(tokens, fh, indent=2)
            fh.write("\n")
        LOG.info("REST-API tokens saved to %s", self.token_spool)

    def ensure_tokens(self, tenant_names):
        tokens = self.load_tokens()
        changed = False

        for tenant_name in tenant_names or []:
            tenant_tokens = tokens.setdefault(tenant_name, {})
            if not isinstance(tenant_tokens, dict):
                tenant_tokens = {}
                tokens[tenant_name] = tenant_tokens
                changed = True

            if not tenant_tokens.get("restapi"):
                tenant_tokens["restapi"] = self.generate_token()
                changed = True
                LOG.info("Generated REST-API token for tenant=%s", tenant_name)

        if changed:
            self.save_tokens(tokens, self.token_spool)

        return tokens
