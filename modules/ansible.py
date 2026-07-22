import asyncio
import logging

import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.tokens import RestAPITokens
from argo_automation_cpas.webapi import WebAPI

LOG = logging.getLogger(__name__)


class Ansible:
    PREFIX_CONN = "connector_"
    PREFIX_POEM = "poem_"

    def __init__(self):
        self.settings = get_settings()
        self.connector_tenant_defaults = {
            k[len(self.PREFIX_CONN) :]: v
            for k, v in self.settings.ansible.defaults.items()
            if k.startswith(self.PREFIX_CONN + "tenant_")
        }
        self.poem_tenant_defaults = {
            k[len(self.PREFIX_POEM) :]: v
            for k, v in self.settings.ansible.defaults.items()
            if k.startswith(self.PREFIX_POEM + "tenant_")
        }
        self.restapi_tokens = RestAPITokens()

    def _poem_extravars(self, component_tokens, add_tenants, remove_tenants):
        extravars = dict()

        if add_tenants is not None:
            restapi_tokens = self.restapi_tokens.ensure_tokens(add_tenants)
            entries = []

            for t in add_tenants:
                entry = {"tenant_name": t}
                # remove hyphen and underscore for PostgreSQL schema creation
                schema_name = t.replace("-", "").replace("_", "").lower()
                entry.update(tenant_schema_name=schema_name)
                tokens = (component_tokens or {}).get(t) or {}
                poem_tokens = {
                    "webapi_ro": tokens.get("poem-viewer"),
                    "webapi_rw": tokens.get("poem-admin"),
                    "restapi": restapi_tokens[t].get("restapi"),
                }
                entry["tokens"] = poem_tokens
                poem_fqdn = f"{t.lower()}.{self.settings.ansible.poem_fqdn_suffix}"
                if poem_fqdn:
                    LOG.info("Set POEM FQDN=%s", poem_fqdn)
                    entry["tenant_fqdn"] = poem_fqdn
                if self.settings.ansible.poem_superuserpassword:
                    self.poem_tenant_defaults["tenant_superuser_password"] = (
                        self.settings.ansible.poem_superuserpassword
                    )
                entries.append({**entry, **self.poem_tenant_defaults})
            extravars["poem_tenants"] = entries
        if remove_tenants is not None:
            extravars["poem_remove_tenants"] = [t for t in remove_tenants]

        return extravars

    def _connector_extravars(self, webapi_overrides, component_tokens, add_tenants, remove_tenants):
        for k, v in (webapi_overrides or {}).items():
            if k.startswith(self.PREFIX_CONN + "tenant_"):
                self.connector_tenant_defaults[k[len(self.PREFIX_CONN) :]] = v

        extravars = {
            k: v
            for k, v in self.settings.ansible.defaults.items()
            if not k.startswith(self.PREFIX_CONN + "tenant_")
        }
        if self.settings.ansible.user_connector:
            extravars["user_connector"] = self.settings.ansible.user_connector
        if self.settings.ansible.group_connector:
            extravars["group_connector"] = self.settings.ansible.group_connector

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
                    LOG.info(
                        "Set tenant_webapi_token for tenant=%s from component_tokens",
                        key,
                    )
                if (
                    self.settings.ansible.connectors_default_service_type
                    and entry.get("tenant_topo_type", "").lower() == "PROVIDER".lower()
                ):
                    entry["tenant_topo_defaultservicetype"] = (
                        self.settings.ansible.connectors_default_service_type
                    )
                entries.append(entry)

            extravars["connector_tenants"] = entries

        if remove_tenants is not None:
            extravars["connector_remove_tenants"] = [t.upper() for t in remove_tenants]

        return extravars

    async def run(
        self,
        playbook,
        inventory=None,
        webapi_overrides=None,
        component_tokens=None,
        add_tenants=None,
        remove_tenants=None,
        show_artifacts=None,
    ):
        private_key = self.settings.ansible.ssh_private_key
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self.settings.ansible_private_data_dir,
            playbook,
            inventory or "default",
            private_key or "none",
        )

        if component_tokens is None:
            webapi = WebAPI()
            component_tokens = webapi.tokens.load_tokens(self.settings.webapi.tokens_spool)
            if component_tokens:
                LOG.info(
                    "Loaded tokens from spool %s for tenants: %s",
                    self.settings.webapi.tokens_spool,
                    ", ".join(sorted(component_tokens.keys())),
                )

        extravars = None
        if playbook.startswith("connectors"):
            extravars = self._connector_extravars(
                webapi_overrides, component_tokens, add_tenants, remove_tenants
            )
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

        return (status == "successful" and rc == 0, kwargs)
