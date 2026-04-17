import asyncio
import logging
import os

from argo_automation_cpas.ams import AMS
from argo_automation_cpas.ansible import Ansible
from argo_automation_cpas.artifacts import clean_artifacts
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.iam import IAM
from argo_automation_cpas.statusapi import StatusAPI
from argo_automation_cpas.webapi import WebAPI


LOG = logging.getLogger(__name__)


def _event_playbook(settings, event):
    """Return (playbook, inventory) for an AMS event name, or (None, None)."""
    if event == "INIT_TOPOLOGY_CONNECTOR":
        return settings.ansible.connectors_playbook, settings.ansible.connectors_inventory
    return None, None


class Application:
    def __init__(self, only_ansible=None, only_ams=False, filter_events=False,
                 only_webapi=False, only_iam=False, only_statusapi=None,
                 update_status=None, event=None, message=None, inventory=None,
                 show_artifacts=None, clean_artifacts=None,
                 rewind=None, add_tenants=None, remove_tenants=None):
        self.settings = get_settings()
        self.only_ansible = only_ansible
        self.only_ams = only_ams
        self.filter_events = filter_events
        self.only_webapi = only_webapi
        self.only_iam = only_iam
        self.only_statusapi = only_statusapi
        self.update_status = update_status
        self.event = event
        self.message = message
        self.inventory = inventory
        self.show_artifacts = show_artifacts
        self.clean_artifacts = clean_artifacts
        self.rewind = rewind
        self.add_tenants = add_tenants
        self.remove_tenants = remove_tenants

    async def run(self):
        if self.clean_artifacts is not None:
            artifacts_dir = os.path.join(self.settings.ansible_private_data_dir, "artifacts")
            clean_artifacts(artifacts_dir, self.clean_artifacts)
            return

        if self.only_ansible is not None:
            ansible = Ansible()
            await ansible.run(
                self.only_ansible,
                inventory=self.inventory,
                add_tenants=self.add_tenants,
                remove_tenants=self.remove_tenants,
                show_artifacts=self.show_artifacts,
            )
            return

        if self.only_webapi:
            webapi = WebAPI()
            await webapi.run()
            return

        if self.only_iam:
            iam = IAM()
            try:
                token = await iam.fetch_token()
                if token:
                    print(token)
            finally:
                await iam.close()
            return

        if self.only_statusapi is not None:
            iam = IAM()
            status_api = StatusAPI()
            try:
                token = await iam.fetch_token()
                if self.update_status is not None:
                    if not self.event:
                        LOG.error("--update-status requires --event")
                        raise SystemExit(2)
                    kwargs = {}
                    if self.message is not None:
                        kwargs["message"] = self.message
                    await status_api.update_job_status(
                        self.only_statusapi,
                        self.event, self.update_status, token, **kwargs,
                    )
                else:
                    await status_api.fetch_status(self.only_statusapi, token)
            finally:
                await iam.close()
                await status_api.close()
            return

        if self.only_ams:
            ams = await asyncio.to_thread(AMS().init)
            if self.rewind is not None:
                await asyncio.to_thread(ams.rewind_offset, self.rewind)
            await ams.pull_and_print(filter_events=self.filter_events)
            return

        ams = await asyncio.to_thread(AMS().init)

        payloads = await ams.pull_messages()
        if not payloads:
            return

        webapi = WebAPI()
        iam = IAM()
        status_api = StatusAPI()
        ansible = Ansible()

        try:
            token = await iam.fetch_token()
            component_tokens = await webapi.refresh_tokens()
            if any(component_tokens.values()):
                webapi.save_tokens(component_tokens, self.settings.webapi.tokens_spool)
            connector_token = webapi.find_connector_token(component_tokens)
            webapi_overrides = await webapi.fetch_topology_config(
                self.settings.webapi.url_api_config, token=connector_token
            )

            for payload in payloads:
                props = payload.get("properties", {})
                tenant_name = props["tenant_name"]
                tenant_id = props["tenant_id"]
                event = payload.get("name")
                LOG.info("Processing tenant_name=%s tenant_id=%s name=%s",
                         tenant_name, tenant_id, event)

                playbook, event_inventory = _event_playbook(self.settings, event)
                if not playbook:
                    LOG.info(
                        "Skipping tenant_name=%s event=%s: no playbook mapping",
                        tenant_name, event,
                    )
                    continue

                current_status = await status_api.get_job_status(
                    tenant_id, event, token
                )
                if current_status != "INITIALISED":
                    LOG.info(
                        "Skipping tenant_name=%s event=%s: status=%s (expected INITIALISED)",
                        tenant_name, event, current_status,
                    )
                    continue

                await status_api.update_job_status(
                    tenant_id, event, "IN_PROGRESS", token,
                )
                ok = await ansible.run(
                    playbook,
                    inventory=self.inventory or event_inventory,
                    webapi_overrides=webapi_overrides,
                    component_tokens=component_tokens,
                    add_tenants=self.add_tenants or [tenant_name],
                    remove_tenants=self.remove_tenants,
                    show_artifacts=self.show_artifacts,
                )
                if ok:
                    await status_api.update_job_status(
                        tenant_id, event, "COMPLETED", token,
                        message=(
                            "Connector successfully configured for tenant %s "
                            "by argo-automation-cpas" % tenant_name
                        ),
                    )
                else:
                    LOG.warning(
                        "Ansible run failed for tenant_name=%s event=%s",
                        tenant_name, event,
                    )
                    await status_api.update_job_status(
                        tenant_id, event, "FAILED", token,
                        message=(
                            "Connector configuration failed for tenant %s "
                            "by argo-automation-cpas" % tenant_name
                        ),
                    )
        finally:
            await webapi.close()
            await iam.close()
            await status_api.close()
