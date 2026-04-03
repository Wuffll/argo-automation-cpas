import asyncio
import logging
import os

from argo_automation_cpas import ams as ams_mod
from argo_automation_cpas import ansible, iam, statusapi, webapi
from argo_automation_cpas.artifacts import clean_artifacts
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

    async def run(self):
        if self.clean_artifacts is not None:
            artifacts_dir = os.path.join(self.settings.ansible_private_data_dir, "artifacts")
            clean_artifacts(artifacts_dir, self.clean_artifacts)
            return

        if self.only_ansible is not None:
            await ansible.run(self.settings, self.only_ansible, inventory=self.inventory,
                              show_artifacts=self.show_artifacts)
            return

        if self.only_webapi:
            await webapi.run(self.settings)
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
            webapi_overrides = await webapi.fetch_topology_config(
                webapi_session, self.settings.webapi.url_api_config
            )
            await ansible.run(
                self.settings, self.settings.ansible_playbook,
                inventory=self.inventory,
                webapi_overrides=webapi_overrides,
                add_tenants=self.add_tenants,
                remove_tenants=self.remove_tenants,
                show_artifacts=self.show_artifacts,
            )
