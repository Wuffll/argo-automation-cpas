import json
import logging
import os
import secrets
import string

LOG = logging.getLogger(__name__)

DEFAULT_RESTAPI_TOKENS_SPOOL = "/opt/argo-automation-cpas/var/spool/restapi_tokens.json"
RESTAPI_TOKEN_LENGTH = 32
RESTAPI_TOKEN_ALPHABET = string.ascii_letters + string.digits


class RestAPITokens:
    def generate_token(self, length=RESTAPI_TOKEN_LENGTH):
        return "".join(secrets.choice(RESTAPI_TOKEN_ALPHABET) for _ in range(length))

    def load_tokens(self, path=DEFAULT_RESTAPI_TOKENS_SPOOL):
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
            LOG.warning("REST-API token spool is not a mapping: %s", path)
        except (OSError, json.JSONDecodeError) as exc:
            LOG.warning("Failed to load REST-API tokens from %s: %s", path, exc)
        return {}

    def save_tokens(self, tokens, path=DEFAULT_RESTAPI_TOKENS_SPOOL):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(tokens, fh, indent=2)
            fh.write("\n")
        LOG.info("REST-API tokens saved to %s", path)

    def ensure_tokens(self, tenant_names, path=DEFAULT_RESTAPI_TOKENS_SPOOL):
        tokens = self.load_tokens(path)
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
            self.save_tokens(tokens, path)

        return tokens
