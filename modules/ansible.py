import asyncio
import logging

import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.webapi import WebAPI

LOG = logging.getLogger(__name__)


class Ansible:
    def __init__(self):
        self.settings = get_settings()

    async def run(self, playbook, inventory=None, webapi_overrides=None, component_tokens=None,
                  add_tenants=None, remove_tenants=None, show_artifacts=None):
        private_key = self.settings.ansible.ssh_private_key
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self.settings.ansible_private_data_dir,
            playbook,
            inventory or "default",
            private_key or "none",
        )

        defaults = self.settings.ansible.defaults

        # Keys prefixed with "connector_tenant_" become per-tenant defaults
        # e.g. connector_tenant_topo_type -> tenant_topo_type
        _PREFIX = "connector_"
        tenant_defaults = {
            k[len(_PREFIX):]: v
            for k, v in defaults.items()
            if k.startswith(_PREFIX + "tenant_")
        }

        # webapi overrides take precedence over roles-defaults.yml
        for k, v in (webapi_overrides or {}).items():
            if k.startswith(_PREFIX + "tenant_"):
                tenant_defaults[k[len(_PREFIX):]] = v

        extravars = {k: v for k, v in defaults.items() if not k.startswith(_PREFIX + "tenant_")}
        if self.settings.ansible.user_connector:
            extravars["user_connector"] = self.settings.ansible.user_connector
        if self.settings.ansible.group_connector:
            extravars["group_connector"] = self.settings.ansible.group_connector

        # Fall back to the webapi tokens spool when not provided explicitly
        # (e.g. manual --only-ansible runs skip the webapi refresh step).
        if component_tokens is None:
            component_tokens = WebAPI.load_tokens(self.settings.webapi.tokens_spool)
            if component_tokens:
                LOG.info("Loaded connector tokens from spool %s for tenants: %s",
                         self.settings.webapi.tokens_spool,
                         ", ".join(sorted(component_tokens.keys())))

        # Build a case-insensitive lookup {TENANT_UPPER: webapi_token} from the
        # "connector" component entries in component_tokens.
        webapi_token_by_tenant = {}
        if component_tokens:
            for tenant_name, components in component_tokens.items():
                for component, token in (components or {}).items():
                    if "connector" in component and token:
                        webapi_token_by_tenant[tenant_name.upper()] = token
                        break

        if add_tenants is not None:
            entries = []
            for t in add_tenants:
                key = t.upper()
                entry = {"tenant_name": key, **tenant_defaults}
                if key in webapi_token_by_tenant:
                    entry["tenant_webapi_token"] = webapi_token_by_tenant[key]
                    LOG.info("Set tenant_webapi_token for tenant=%s from component_tokens", key)
                entries.append(entry)
            extravars["connector_tenants"] = entries
        if remove_tenants is not None:
            extravars["connector_remove_tenants"] = [t.upper() for t in remove_tenants]

        envvars = {}
        if self.settings.general.strip_ansi:
            envvars["ANSIBLE_NOCOLOR"] = "1"

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            playbook=playbook,
            quiet=True,
            envvars=envvars,
        )

        if extravars:
            kwargs["extravars"] = extravars
        if inventory:
            kwargs["inventory"] = inventory
        if private_key:
            kwargs["cmdline"] = "--private-key %s" % private_key

        runner = await asyncio.to_thread(ansible_runner.run, **kwargs)

        status = getattr(runner, "status", "unknown")
        rc = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)

        if show_artifacts is not None:
            print_artifacts(runner, show_artifacts)

        return status == "successful" and rc == 0
