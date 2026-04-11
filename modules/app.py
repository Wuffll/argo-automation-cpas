import asyncio
import logging
import os

from argo_automation_cpas import ams as ams_mod
from argo_automation_cpas import ansible, iam, only, statusapi, webapi
from argo_automation_cpas.artifacts import clean_artifacts
from argo_automation_cpas.http import client_session


LOG = logging.getLogger(__name__)


def _event_playbook(settings, event):
    """Return (playbook, inventory) for an AMS event name, or (None, None)."""
    if event == "INIT_TOPOLOGY_CONNECTOR":
        return settings.ansible.connectors_playbook, settings.ansible.connectors_inventory
    return None, None


class Application:
    def __init__(self, settings, only_ansible=None, only_ams=False, filter_events=False,
                 only_webapi=False, only_iam=False, only_statusapi=None,
                 update_status=None, event=None, message=None, inventory=None,
                 show_artifacts=None, clean_artifacts=None,
                 add_tenants=None, remove_tenants=None):
        self.settings = settings
        self.only_ansible = only_ansible  # None or playbook filename string
        self.only_ams = only_ams          # True = pull AMS message, print and exit
        self.filter_events = filter_events  # True = filter --only-ams output by tenant/event
        self.only_webapi = only_webapi    # True = refresh webapi tokens and exit
        self.only_iam = only_iam          # True = fetch IAM token, print and exit
        self.only_statusapi = only_statusapi  # None or tenant_id string
        self.update_status = update_status  # None or status string (e.g. IN_PROGRESS)
        self.event = event                # None or event name (e.g. INIT_TOPOLOGY_CONNECTOR)
        self.message = message            # None or override job message
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
            await only.run_ansible(
                self.settings, self.only_ansible,
                inventory=self.inventory,
                add_tenants=self.add_tenants,
                remove_tenants=self.remove_tenants,
                show_artifacts=self.show_artifacts,
            )
            return

        if self.only_webapi:
            await only.run_webapi(self.settings)
            return

        if self.only_iam:
            await only.run_iam(self.settings)
            return

        if self.only_statusapi is not None:
            await only.run_statusapi(
                self.settings, self.only_statusapi,
                update_status=self.update_status,
                event=self.event,
                message=self.message,
            )
            return

        if self.only_ams:
            await only.run_ams(self.settings, filter_events=self.filter_events)
            return

        ams = await asyncio.to_thread(ams_mod.init_ams, self.settings)

        payloads = await ams_mod.pull_messages(ams, self.settings)
        if not payloads:
            return

        async with (
            client_session(self.settings, base_url=self.settings.webapi.url) as webapi_session,
            client_session(self.settings) as iam_session,
            client_session(self.settings) as statusapi_session,
        ):
            await webapi.probe(webapi_session, self.settings.webapi.url)
            token = await iam.fetch_token(iam_session, self.settings)
            component_tokens = await webapi.refresh_tokens(webapi_session, self.settings)
            if any(component_tokens.values()):
                webapi.save_tokens(component_tokens, self.settings.webapi.tokens_spool)
            connector_token = webapi.find_connector_token(component_tokens)
            webapi_overrides = await webapi.fetch_topology_config(
                webapi_session, self.settings.webapi.url_api_config, token=connector_token
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

                current_status = await statusapi.get_job_status(
                    statusapi_session, self.settings, tenant_id, event, token
                )
                if current_status != "INITIALISED":
                    LOG.info(
                        "Skipping tenant_name=%s event=%s: status=%s (expected INITIALISED)",
                        tenant_name, event, current_status,
                    )
                    continue

                await statusapi.update_job_status(
                    statusapi_session, self.settings, tenant_id,
                    event, "IN_PROGRESS", token,
                )
                ok = await ansible.run(
                    self.settings, playbook,
                    inventory=self.inventory or event_inventory,
                    webapi_overrides=webapi_overrides,
                    component_tokens=component_tokens,
                    add_tenants=self.add_tenants,
                    remove_tenants=self.remove_tenants,
                    show_artifacts=self.show_artifacts,
                )
                if ok:
                    await statusapi.update_job_status(
                        statusapi_session, self.settings, tenant_id,
                        event, "COMPLETED", token,
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
                    await statusapi.update_job_status(
                        statusapi_session, self.settings, tenant_id,
                        event, "FAILED", token,
                        message=(
                            "Connector configuration failed for tenant %s "
                            "by argo-automation-cpas" % tenant_name
                        ),
                    )
