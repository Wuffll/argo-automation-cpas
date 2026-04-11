import asyncio
import logging

from argo_automation_cpas import ams as ams_mod
from argo_automation_cpas import ansible, iam, statusapi, webapi
from argo_automation_cpas.http import client_session


LOG = logging.getLogger(__name__)


async def run_ansible(settings, playbook, inventory=None,
                      add_tenants=None, remove_tenants=None, show_artifacts=None):
    await ansible.run(
        settings, playbook,
        inventory=inventory,
        add_tenants=add_tenants,
        remove_tenants=remove_tenants,
        show_artifacts=show_artifacts,
    )


async def run_webapi(settings):
    await webapi.run(settings)


async def run_iam(settings):
    async with client_session(settings) as session:
        token = await iam.fetch_token(session, settings)
        if token:
            print(token)


async def run_statusapi(settings, tenant_id, update_status=None, event=None, message=None):
    async with (
        client_session(settings) as iam_session,
        client_session(settings) as statusapi_session,
    ):
        token = await iam.fetch_token(iam_session, settings)
        if update_status is not None:
            if not event:
                LOG.error("--update-status requires --event")
                raise SystemExit(2)
            kwargs = {}
            if message is not None:
                kwargs["message"] = message
            await statusapi.update_job_status(
                statusapi_session, settings, tenant_id,
                event, update_status, token, **kwargs,
            )
        else:
            await statusapi.fetch_status(
                statusapi_session, settings, tenant_id, token
            )


async def run_ams(settings, filter_events=False):
    ams = await asyncio.to_thread(ams_mod.init_ams, settings)
    await ams_mod.pull_and_print(ams, settings, filter_events=filter_events)
