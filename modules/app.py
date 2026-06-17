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
from argo_automation_cpas.monboxgit import (
    MonboxGit,
    NewTenantAgentInfo,
    NewTenantBackendInfo,
)

from argo_automation_cpas.restapi_tokens import RestAPITokens

LOG = logging.getLogger(__name__)


def _event_playbook(settings, event):
    """Return (playbook, inventory) for an AMS event name, or (None, None)."""
    if event == "INIT_TOPOLOGY_CONNECTOR":
        return (
            settings.ansible.connectors_playbook,
            settings.ansible.connectors_inventory,
        )
    if event == "INIT_POEM":
        return settings.ansible.poem_playbook, settings.ansible.poem_inventory
    return None, None


def _is_event_init_monbox(event):
    return event == "INIT_MONITORING_BOX"


class Application:
    def __init__(
        self,
        only_ansible=None,
        only_ams=False,
        filter_events=False,
        only_webapi=False,
        only_iam=False,
        only_statusapi=None,
        only_monbox_git=None,
        update_status=None,
        event=None,
        message=None,
        inventory=None,
        show_artifacts=None,
        clean_artifacts=None,
        offset=None,
        add_tenants=None,
        remove_tenants=None,
    ):
        self.settings = get_settings()
        self.only_ansible = only_ansible
        self.only_ams = only_ams
        self.filter_events = filter_events
        self.only_webapi = only_webapi
        self.only_iam = only_iam
        self.only_statusapi = only_statusapi
        self.only_monbox_git = only_monbox_git
        self.update_status = update_status
        self.event = event
        self.message = message
        self.inventory = inventory
        self.show_artifacts = show_artifacts
        self.clean_artifacts = clean_artifacts
        self.offset = offset
        self.add_tenants = add_tenants
        self.remove_tenants = remove_tenants

    async def run(self):
        if self.clean_artifacts is not None:
            artifacts_dir = os.path.join(
                self.settings.ansible_private_data_dir, "artifacts"
            )
            clean_artifacts(artifacts_dir, self.clean_artifacts)
            return

        if self.only_ansible is not None:
            ansible = Ansible()
            ok, extravars = await ansible.run(
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
                        self.event,
                        self.update_status,
                        token,
                        **kwargs,
                    )
                else:
                    await status_api.fetch_status(self.only_statusapi, token)
            finally:
                await iam.close()
                await status_api.close()
            return

        if self.only_ams:
            ams = await asyncio.to_thread(AMS().init)
            if self.offset is not None:
                await asyncio.to_thread(ams.move_offset, self.offset)
            await ams.pull_and_print(filter_events=self.filter_events)

            print("Only AMS | Refreshing AMS tokens!")
            try:
                ams_component_tokens = await ams.refresh_tokens()
                if any(ams_component_tokens.values()):
                    ams.save_tokens(
                        ams_component_tokens, self.settings.ams.tokens_spool
                    )
            finally:
                await ams.close()

            return

        if self.only_monbox_git:
            print(
                "Only MonboxGit | You are running the initialization of monbox-git only!"
            )
            monboxgit = MonboxGit()

            tenant_names = self.settings.automation.tenants

            if tenant_names is None:
                print("Only MonboxGit | tenant_names is None!")
                return

            ams = await asyncio.to_thread(AMS().init)
            webapi = WebAPI()

            restapi_tokens_client = RestAPITokens()
            restapi_tokens = restapi_tokens_client.load_tokens()

            if restapi_tokens is None:
                print("Only MonboxGit | Error: RestAPI tokens not found!")
                return

            try:
                for tenant_name in tenant_names:
                    await monboxgit.add_new_tenant(
                        webapi, ams, tenant_name, restapi_tokens
                    )

                print("Only Monbox | Successfully commited file changes.")

                success = await monboxgit.commit_new_tenants()

                if not success:
                    print(
                        f"Error: One of the git commits was unsuccessful! Exiting early."
                    )
                    return

                monboxgit.clear_added_tenants()

                await monboxgit.start_monboxgit_runner()

            finally:
                await ams.close()
                await webapi.close()

            return

        ams = await asyncio.to_thread(AMS().init)

        ams_events = await ams.pull_messages()
        if not ams_events:
            return

        webapi = WebAPI()
        iam = IAM()
        status_api = StatusAPI()
        ansible = Ansible()
        monboxgit = MonboxGit()

        restapi_tokens_client = RestAPITokens()
        restapi_tokens = restapi_tokens_client.load_tokens()

        try:
            token = await iam.fetch_token()

            component_tokens = await webapi.refresh_tokens()
            if any(component_tokens.values()):
                webapi.save_tokens(component_tokens, self.settings.webapi.tokens_spool)

            ams_component_tokens = await ams.refresh_tokens()
            if any(ams_component_tokens.values()):
                ams.save_tokens(ams_component_tokens, self.settings.ams.tokens_spool)

            monbox_init_events = []
            for payload in ams_events:
                props = payload.get("properties", {})
                tenant_name = props["tenant_name"]
                tenant_id = props["tenant_id"]
                event = payload.get("name")
                LOG.info(
                    "Processing tenant_name=%s tenant_id=%s name=%s",
                    tenant_name,
                    tenant_id,
                    event,
                )

                playbook, event_inventory = _event_playbook(self.settings, event)

                current_status = await status_api.get_job_status(
                    tenant_id, event, token
                )

                if playbook:
                    if current_status != "INITIALISED":
                        LOG.info(
                            "Skipping tenant_name=%s event=%s: status=%s (expected INITIALISED)",
                            tenant_name,
                            event,
                            current_status,
                        )
                        continue

                    await status_api.update_job_status(
                        tenant_id,
                        event,
                        "IN_PROGRESS",
                        token,
                    )

                    if playbook.startswith("connectors"):
                        connector_token = webapi.find_connector_token(component_tokens)
                        webapi_overrides = await webapi.fetch_topology_config(
                            self.settings.webapi.url_api_config, token=connector_token
                        )
                        ok, _ = await ansible.run(
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
                                tenant_id,
                                event,
                                "COMPLETED",
                                token,
                                message=(
                                    "Connector successfully configured for tenant %s "
                                    "by argo-automation-cpas" % tenant_name
                                ),
                            )
                        else:
                            LOG.warning(
                                "Ansible run failed for tenant_name=%s event=%s",
                                tenant_name,
                                event,
                            )
                            await status_api.update_job_status(
                                tenant_id,
                                event,
                                "FAILED",
                                token,
                                message=(
                                    "Connector configuration failed for tenant %s "
                                    "by argo-automation-cpas" % tenant_name
                                ),
                            )

                    elif playbook.startswith("poem"):
                        ok, extravars = await ansible.run(
                            playbook,
                            inventory=self.inventory or event_inventory,
                            component_tokens=component_tokens,
                            add_tenants=self.add_tenants or [tenant_name],
                            remove_tenants=self.remove_tenants,
                            show_artifacts=self.show_artifacts,
                        )
                        if ok:
                            await status_api.update_job_status(
                                tenant_id,
                                event,
                                "COMPLETED",
                                token,
                                message=(
                                    "POEM successfully configured for tenant %s "
                                    "by argo-automation-cpas" % tenant_name
                                ),
                            )
                        else:
                            LOG.warning(
                                "Ansible run failed for tenant_name=%s event=%s",
                                tenant_name,
                                event,
                            )
                            await status_api.update_job_status(
                                tenant_id,
                                event,
                                "FAILED",
                                token,
                                message=(
                                    "POEM configuration failed for tenant %s "
                                    "by argo-automation-cpas" % tenant_name
                                ),
                            )
                elif _is_event_init_monbox(event):
                    print("Monbox initialization for tenant " + tenant_name)

                    current_status = await status_api.get_job_status(
                        tenant_id, event, token
                    )

                    print(f"Tenant {tenant_name} has status: {current_status}")

                    if current_status != "INITIALISED":
                        LOG.info(
                            "Skipping tenant_name=%s event=%s: status=%s (expected INITIALISED)",
                            tenant_name,
                            event,
                            current_status,
                        )
                        continue

                    # add tenant to list of monbox initialization
                    monbox_init_events.append(payload)

                else:
                    LOG.info(
                        "Skipping tenant_name=%s event=%s: no playbook mapping",
                        tenant_name,
                        event,
                    )

            # processing monbox init events
            start_monbox_init = len(monbox_init_events) > 0
            if start_monbox_init:
                try:
                    await self._process_monbox_init_events(
                        monbox_init_events,
                        monboxgit,
                        webapi,
                        ams,
                        status_api,
                        token,
                        restapi_tokens,
                    )
                except:
                    pass

        finally:
            await ams.close()
            await webapi.close()
            await iam.close()
            await status_api.close()

    async def _process_monbox_init_events(
        self, init_events, monboxgit, webapi, ams, status_api, token, restapi_tokens
    ):
        # set tenants to IN-PROGRESS
        for payload in init_events:
            props = payload.get("properties", {})
            tenant_name = props["tenant_name"]
            tenant_id = props["tenant_id"]
            event = payload.get("name")

            await status_api.update_job_status(
                tenant_id,
                event,
                "IN_PROGRESS",
                token,
            )

            await monboxgit.add_new_tenant(webapi, ams, tenant_name, restapi_tokens)

        # commit new tenant configs to git repo
        monboxgit_success = await monboxgit.commit_new_tenants()
        if not monboxgit_success:
            for payload in init_events:
                props = payload.get("properties", {})
                tenant_id = props["tenant_id"]
                event = payload.get("name")
                await status_api.update_job_status(
                    tenant_id,
                    event,
                    "FAILED",
                    token,
                    message=(
                        f"Error: MonboxGit module was unable to successfully commit new changes for this tenant."
                    ),
                )
            raise RuntimeError(
                "Error: Monbox new tenants commit was unsuccessful! Exiting early."
            )

        # run puppet script on machines
        runner_rc = await monboxgit.start_monboxgit_runner()
        if runner_rc == 1:
            for payload in init_events:
                props = payload.get("properties", {})
                tenant_id = props["tenant_id"]
                event = payload.get("name")
                await status_api.update_job_status(
                    tenant_id,
                    event,
                    "FAILED",
                    token,
                    message=(
                        f"Error: Monbox init ansible run for this tenant was unsuccessful."
                    ),
                )
            raise RuntimeError(
                "Error: Monbox init ansible run was unsuccessful! Exiting early."
            )

        # check if the monbox was initialized on tenants
        print("Making sure monbox inits were successfull... (takes up to 25 mins)")

        monbox_init_check_counter = 5  # number of tries
        monbox_init_check_interval = 5 * 60  # in seconds

        init_check_success = False
        all_tenants_inited = False
        inited_tenants = []
        for i in range(monbox_init_check_counter):
            await asyncio.sleep(monbox_init_check_interval)

            print(f"Monbox init check #{i + 1}")

            all_tenants_inited, inited_tenants = (
                await monboxgit.start_monbox_init_check()
            )
            if all_tenants_inited:
                init_check_success = True
                break

            print(f"Waiting for monbox to successfully init on all tenants")

        if not all_tenants_inited:
            print(f"Warning: Some tenants weren't able to initialize monitoring box!")

        await monboxgit.update_packages_on_backend()
        await monboxgit.update_packages_on_agent()

        for payload in init_events:
            props = payload.get("properties", {})
            tenant_id = props["tenant_id"]
            tenant_name = props["tenant_name"]
            event = payload.get("name")
            if all_tenants_inited or tenant_name.lower() in inited_tenants:
                await status_api.update_job_status(
                    tenant_id,
                    event,
                    "COMPLETED",
                    token,
                )
            else:
                await status_api.update_job_status(
                    tenant_id,
                    event,
                    "FAILED",
                    token,
                    message=(f"Error: Unable to initialize monitoring box."),
                )

        if not init_check_success:
            raise RuntimeError(
                "Error: Monbox check init ansible run was unsuccessful! Exiting early."
            )

        # if monboxes are initialized properly, delete added tenants from to-be-added array
        monboxgit.clear_added_tenants()
