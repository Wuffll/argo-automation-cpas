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
from argo_automation_cpas.monboxgit import MonboxGit

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
        delete_tenant=None,
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
        self.delete_tenant = delete_tenant
        self.update_status = update_status
        self.event = event
        self.message = message
        self.inventory = inventory
        self.show_artifacts = show_artifacts
        self.clean_artifacts = clean_artifacts
        self.offset = offset
        self.add_tenants = add_tenants
        self.remove_tenants = remove_tenants

    async def _process_monbox_init_events(
        self,
        init_events: list,
        monboxgit: MonboxGit,
        webapi,
        ams,
        iam,
        status_api,
        token,
        restapi_tokens,
    ):
        # set tenants to IN-PROGRESS
        for payload in init_events:
            props = payload.get("properties", {})
            tenant_name = props["tenant_name"]
            tenant_id = props["tenant_id"]
            event = payload.get("name")

            added = monboxgit.add_new_tenant(webapi, ams, tenant_name, restapi_tokens)

            # if there is an error or the status api has already been set; skip
            if not added:
                continue

            await status_api.update_job_status(
                tenant_id,
                event,
                "IN_PROGRESS",
                token,
            )

        # commit new tenant configs to git repo
        monboxgit_success = monboxgit.commit_new_tenants()
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
                "Monbox new tenants commit was unsuccessful! Exiting early."
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
                "Monbox init ansible run was unsuccessful! Exiting early."
            )

        # check if the monbox was initialized on tenants
        monbox_init_check_counter = self.settings.monboxgit.init_check_count
        monbox_init_check_interval = self.settings.monboxgit.init_check_interval
        monbox_init_check_max_time = (
            monbox_init_check_counter * monbox_init_check_interval
        ) / 60.0
        monbox_init_check_max_time = round(monbox_init_check_max_time, 2)
        LOG.info(
            f"Making sure monbox inits were successful... (takes up to {monbox_init_check_max_time} mins)"
        )

        init_check_success = False
        all_tenants_inited = False
        inited_tenants = []
        for i in range(monbox_init_check_counter):
            await asyncio.sleep(monbox_init_check_interval)

            LOG.info(f"Monbox init check #{i + 1}")

            all_tenants_inited, inited_tenants = (
                await monboxgit.start_monbox_init_check()
            )
            if all_tenants_inited:
                init_check_success = True
                break

            LOG.info(f"Waiting for monbox to successfully init on all tenants")

        if not all_tenants_inited:
            LOG.info(
                f"Warning: Some tenants weren't able to initialize monitoring box!"
            )

        await monboxgit.update_packages_on_backend()
        await monboxgit.update_packages_on_agent()

        token = await iam.fetch_token()

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
                "Monbox check init ansible run was unsuccessful! Exiting early."
            )

        # if monboxes are initialized properly, delete added tenants from to-be-added array
        monboxgit.clear_added_tenants()

    def _check_if_tenant_filtered_out(self, tenant_name: str):
        if len(self.settings.automation.filter_tenants) != 0:
            for prefix in self.settings.automation.filter_tenants:
                if tenant_name.startswith(prefix):
                    return True

        return False

    def _get_allowed_tenants_from_array(self, tenants_array):
        allowed_tenants = []

        for tenant_name in tenants_array:
            if self._check_if_tenant_filtered_out(tenant_name):
                LOG.info(f"Tenant {tenant_name} filtered out")
            else:
                allowed_tenants.append(tenant_name)

        return allowed_tenants

    def _get_allowed_tenants(self, ams_events):
        allowed_tenants = []

        for payload in ams_events:
            props = payload.get("properties", {})
            tenant_name = props["tenant_name"]
            tenant_id = props["tenant_id"]

            if self._check_if_tenant_filtered_out(tenant_name):
                LOG.info(f"Tenant {tenant_name} (id: {tenant_id}) filtered out")
            else:
                allowed_tenants.append(tenant_name)

        return allowed_tenants

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

            config_filter_tenants = self.settings.automation.tenants

            allowed_tenants = []
            if len(config_filter_tenants) != 0:
                allowed_tenants = self._get_allowed_tenants_from_array(
                    config_filter_tenants
                )
            else:
                ams = AMS()
                ams_events = ams.pull_messages()
                allowed_tenants = self._get_allowed_tenants(ams_events)

            await webapi.run(allowed_tenants)

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
            ams = AMS()
            if self.offset is not None:
                ams.move_offset(self.offset)
            ams.pull_and_print(filter_events=self.filter_events)

            config_filter_tenants = self.settings.automation.tenants

            allowed_tenants = []
            if len(config_filter_tenants) != 0:
                allowed_tenants = self._get_allowed_tenants_from_array(
                    config_filter_tenants
                )
            else:
                ams_events = ams.pull_messages()
                allowed_tenants = self._get_allowed_tenants(ams_events)

            LOG.info("Only AMS | Refreshing AMS tokens!")
            ams_component_tokens = await ams.tokens.refresh_tokens(allowed_tenants)
            if any(ams_component_tokens.values()):
                ams.tokens.save_tokens(
                    ams_component_tokens, self.settings.ams.tokens_spool
                )
            return

        if self.only_monbox_git:
            LOG.info("Running OnlyMonboxGit")
            monboxgit = MonboxGit()

            run_delete_tenant = not self.delete_tenant is None
            valid_delete_tenant = self.delete_tenant != ""

            if run_delete_tenant:
                if valid_delete_tenant:
                    LOG.info(f"OnlyMonboxGit | Removing tenant {self.delete_tenant}")
                    monboxgit.remove_tenant(self.delete_tenant)
                    await monboxgit.start_monboxgit_runner()
                else:
                    LOG.error(
                        "OnlyMonboxGit | Invalid tenant_name provided for delete_tenant. Exiting early."
                    )

                return

            tenant_names = self.settings.automation.tenants

            if len(tenant_names) == 0:
                LOG.error(
                    "Only MonboxGit | tenant_names array is empty. Exiting early."
                )
                return

            ams = AMS()
            webapi = WebAPI()

            restapi_tokens_client = RestAPITokens()
            restapi_tokens = restapi_tokens_client.load_tokens()

            if restapi_tokens is None:
                LOG.error("Only MonboxGit | RestAPI tokens not found!")
                return

            try:
                for tenant_name in tenant_names:
                    monboxgit.add_new_tenant(webapi, ams, tenant_name, restapi_tokens)

                success = monboxgit.commit_new_tenants()
                if not success:
                    LOG.error("One of the git commits was unsuccessful! Exiting early.")
                    return

                LOG.info("Only Monbox | Successfully commited file changes.")

                monboxgit.clear_added_tenants()

                await monboxgit.start_monboxgit_runner()

            finally:
                await webapi.close()

            return

        ams = AMS()
        ams_events = ams.pull_messages()

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

            allowed_tenants = self._get_allowed_tenants(ams_events)

            component_tokens = await webapi.refresh_tokens(allowed_tenants)
            if any(component_tokens.values()):
                webapi.save_tokens(component_tokens, self.settings.webapi.tokens_spool)

            ams_component_tokens = await ams.refresh_tokens(allowed_tenants)
            if any(ams_component_tokens.values()):
                ams.save_tokens(ams_component_tokens, self.settings.ams.tokens_spool)

            monbox_init_events = []
            for payload in ams_events:
                props = payload.get("properties", {})
                tenant_name = props["tenant_name"]
                tenant_id = props["tenant_id"]
                event = payload.get("name")

                if self._check_if_tenant_filtered_out(tenant_name):
                    LOG.info(
                        f"Info: Tenant {tenant_name} (id: {tenant_id}) filtered out"
                    )
                    continue

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
                    LOG.info("Monbox initialization candidate tenant: " + tenant_name)

                    current_status = await status_api.get_job_status(
                        tenant_id, event, token
                    )

                    LOG.info(f"Tenant {tenant_name} has status: {current_status}")

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
                        iam,
                        status_api,
                        token,
                        restapi_tokens,
                    )
                except:
                    pass

        finally:
            await webapi.close()
            await iam.close()
            await status_api.close()
