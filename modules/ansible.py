import asyncio
import logging

import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.webapi import WebAPI

LOG = logging.getLogger(__name__)


class Ansible:
    PREFIX = "connector_"

    def __init__(self):
        self.settings = get_settings()
        self.connector_tenant_defaults = {
            k[len(self.PREFIX):]: v
            for k, v in self.settings.ansible.defaults.items()
            if k.startswith(self.PREFIX + "tenant_")
        }

    def _poem_extravars(self, component_tokens, add_tenants, remove_tenants):
        extravars = dict()

        if add_tenants is not None:
            entries = []
            for t in add_tenants:
                key = t.upper()
                entry = {"tenant_name": key}
                if key in component_tokens:
                    tokens = component_tokens[key]
                poem_tokens = dict()
                poem_tokens = {
                    'webapi_ro': component_tokens[key].get('poem-viewer'),
                    'webapi_rw': component_tokens[key].get('poem-admin')
                }
                entry["tokens"] = poem_tokens
                poem_fqdn = f'{t}.{self.settings.ansible.poem_fqdn_suffix}'
                if poem_fqdn:
                    LOG.info("Set POEM FQDN=%s", poem_fqdn)
                    entry["tenant_fqdn"] = poem_fqdn
                entries.append(entry)
            extravars["poem_tenants"] = entries
        if remove_tenants is not None:
            extravars["poem_remove_tenants"] = [t.upper() for t in remove_tenants]

        return extravars

    def _connector_extravars(self, webapi_overrides, component_tokens, add_tenants, remove_tenants):
        # Keys prefixed with "connector_tenant_" become per-tenant defaults
        # e.g. connector_tenant_topo_type -> tenant_topo_type

        # webapi overrides take precedence over roles-defaults.yml
        for k, v in (webapi_overrides or {}).items():
            if k.startswith(self.PREFIX + "tenant_"):
                self.connector_tenant_defaults[k[len(self.PREFIX):]] = v

        extravars = {k: v for k, v in self.settings.ansible.defaults.items() if not k.startswith(self.PREFIX + "tenant_")}
        if self.settings.ansible.user_connector:
            extravars["user_connector"] = self.settings.ansible.user_connector
        if self.settings.ansible.group_connector:
            extravars["group_connector"] = self.settings.ansible.group_connector

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
                entry = {"tenant_name": key, **self.connector_tenant_defaults}
                if key in webapi_token_by_tenant:
                    entry["tenant_webapi_token"] = webapi_token_by_tenant[key]
                    LOG.info("Set tenant_webapi_token for tenant=%s from component_tokens", key)
                entries.append(entry)
            extravars["connector_tenants"] = entries
        if remove_tenants is not None:
            extravars["connector_remove_tenants"] = [t.upper() for t in remove_tenants]

        return extravars

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

        # Fall back to the webapi tokens spool when not provided explicitly
        # (e.g. manual --only-ansible runs skip the webapi refresh step).
        if component_tokens is None:
            component_tokens = WebAPI.load_tokens(self.settings.webapi.tokens_spool)
            if component_tokens:
                LOG.info("Loaded tokens from spool %s for tenants: %s",
                         self.settings.webapi.tokens_spool,
                         ", ".join(sorted(component_tokens.keys())))

        if playbook.startswith("connectors"):
            extravars = self._connector_extravars(webapi_overrides, component_tokens, add_tenants, remove_tenants)
        if playbook.startswith("poem"):
            extravars = self._poem_extravars(component_tokens, add_tenants, remove_tenants)

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
