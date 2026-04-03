import asyncio
import logging
import os

import ansible_runner

from argo_automation_cpas import ams as ams_mod
from argo_automation_cpas import iam, statusapi, webapi
from argo_automation_cpas.artifacts import clean_artifacts, print_artifacts
from argo_automation_cpas.http import client_session
from argo_automation_cpas.messaging import init_ams


LOG = logging.getLogger(__name__)


class Application:
    def __init__(self, settings, only_ansible=None, only_ams=False, only_webapi=False, only_iam=False, only_statusapi=None, inventory=None,
                 show_artifacts=None, clean_artifacts=None,
                 add_tenants=None, remove_tenants=None):
        self.settings = settings
        self.only_ansible = only_ansible  # None or playbook filename string
        self.only_ams = only_ams          # True = pull AMS message, print and exit
        self.only_webapi = only_webapi    # True = refresh webapi tokens and exit
        self.only_iam = only_iam          # True = fetch IAM token, print and exit
        self.only_statusapi = only_statusapi  # None or tenant_id string
        self.inventory = inventory  # None or path to inventory file/directory
        self.show_artifacts = show_artifacts  # None=off, []=all, ['role1',...]=filtered
        self.clean_artifacts = clean_artifacts  # None=off, []=all, ['role1',...]=filtered
        self.add_tenants = add_tenants  # None or list of tenant names
        self.remove_tenants = remove_tenants  # None or list of tenant names
        self._webapi_overrides = {}  # connector_tenant_* overrides from webapi

    async def run(self):
        if self.clean_artifacts is not None:
            artifacts_dir = os.path.join(self.settings.ansible_private_data_dir, "artifacts")
            clean_artifacts(artifacts_dir, self.clean_artifacts)
            return

        if self.only_ansible is not None:
            await self._run_ansible(self.only_ansible)
            return

        if self.only_webapi:
            await self._run_only_webapi()
            return

        if self.only_iam:
            async with client_session(self.settings) as session:
                token = await iam.fetch_token(session, self.settings)
                if token:
                    print(token)
            return

        if self.only_statusapi is not None:
            async with (
                client_session(self.settings) as iam_session,
                client_session(self.settings) as statusapi_session,
            ):
                token = await iam.fetch_token(iam_session, self.settings)
                await statusapi.fetch_status(statusapi_session, self.settings, self.only_statusapi, token)
            return

        ams = await asyncio.to_thread(init_ams, self.settings)

        if self.only_ams:
            await ams_mod.pull_and_print(ams, self.settings)
            return

        payload = await ams_mod.pull_message(ams, self.settings)
        if payload is None:
            return

        tenant_name = payload["tenant_name"]
        tenant_id = payload["tenant_id"]
        LOG.info("Processing tenant_name=%s tenant_id=%s", tenant_name, tenant_id)

        async with (
            client_session(self.settings, base_url=self.settings.webapi.url) as webapi_session,
            client_session(self.settings) as iam_session,
            client_session(self.settings) as statusapi_session,
        ):
            await webapi.probe(webapi_session, self.settings.webapi.url)
            token = await iam.fetch_token(iam_session, self.settings)
            await statusapi.report_status(statusapi_session, self.settings, tenant_id, "IN_PROGRESS", token)
            self._webapi_overrides = await webapi.fetch_topology_config(
                webapi_session, self.settings.webapi.url_api_config
            )
            await self._run_ansible(self.settings.ansible_playbook)

    async def _run_only_webapi(self):
        async with client_session(self.settings, base_url=self.settings.webapi.url) as session:
            tokens = await webapi.refresh_tokens(session, self.settings)
            if any(tokens.values()):
                webapi.save_tokens(tokens, self.settings.webapi.tokens_spool)

            connector_token = webapi.find_connector_token(tokens)
            if connector_token:
                await webapi.fetch_topology_config(
                    session, self.settings.webapi.url_api_config, token=connector_token
                )

    async def _run_ansible(self, playbook):
        private_key = self.settings.ansible.ssh_private_key
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self.settings.ansible_private_data_dir,
            playbook,
            self.inventory or "default",
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
        for k, v in self._webapi_overrides.items():
            if k.startswith(_PREFIX + "tenant_"):
                tenant_defaults[k[len(_PREFIX):]] = v

        extravars = {k: v for k, v in defaults.items() if not k.startswith(_PREFIX + "tenant_")}
        if self.settings.ansible.user_connector:
            extravars["user_connector"] = self.settings.ansible.user_connector
        if self.settings.ansible.group_connector:
            extravars["group_connector"] = self.settings.ansible.group_connector

        if self.add_tenants is not None:
            extravars["connector_tenants"] = [
                {"tenant_name": t.upper(), **tenant_defaults}
                for t in self.add_tenants
            ]
        if self.remove_tenants is not None:
            extravars["connector_remove_tenants"] = [t.upper() for t in self.remove_tenants]

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            playbook=playbook,
            quiet=True,
        )

        if self.settings.ansible.tokens:
            extravars["connector_tokens"] = self.settings.ansible.tokens

        if extravars:
            kwargs["extravars"] = extravars
        if self.inventory:
            kwargs["inventory"] = self.inventory
        if private_key:
            kwargs["cmdline"] = "--private-key %s" % private_key

        runner = await asyncio.to_thread(ansible_runner.run, **kwargs)

        status = getattr(runner, "status", "unknown")
        rc = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)

        if self.show_artifacts is not None:
            print_artifacts(runner, self.show_artifacts)
