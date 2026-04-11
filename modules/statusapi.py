import json
import logging
from datetime import datetime, timezone

import aiohttp

from argo_automation_cpas.http import retrying_request

LOG = logging.getLogger(__name__)

JOB_PICKED_UP_MESSAGE = "Event picked up by argo-automation-cpas"


async def report_status(session, settings, tenant_id, status, token):
    url = settings.statusapi.api.format(tenant_id=tenant_id)
    LOG.info("Reporting status=%s for tenant_id=%s to %s", status, tenant_id, url)
    headers = {"Authorization": "Bearer %s" % token} if token else {}
    try:
        async with retrying_request(
            lambda: session.patch(url, json={"status": status}, headers=headers)
        ) as response:
            response.raise_for_status()
            LOG.info("Status reported: tenant_id=%s status=%s", tenant_id, status)
    except aiohttp.ClientError as exc:
        LOG.warning("Failed to report status to statusapi: %s", exc)


async def update_job_status(session, settings, tenant_id, event, status, token,
                            message=JOB_PICKED_UP_MESSAGE):
    url = settings.statusapi.api.format(tenant_id=tenant_id)
    now = datetime.now(timezone.utc).isoformat()
    body = {
        "jobs": [
            {
                "name": event,
                "status": status,
                "start": now,
                "end": now,
                "message": message,
            }
        ]
    }
    LOG.info("Updating job status tenant_id=%s event=%s status=%s at %s",
             tenant_id, event, status, url)
    headers = {"Authorization": "Bearer %s" % token} if token else {}
    try:
        async with retrying_request(
            lambda: session.patch(url, json=body, headers=headers)
        ) as response:
            response.raise_for_status()
            LOG.info("Job status updated: tenant_id=%s event=%s status=%s",
                     tenant_id, event, status)
    except aiohttp.ClientError as exc:
        LOG.warning("Failed to update job status: %s", exc)


async def fetch_status(session, settings, tenant_id, token):
    url = settings.statusapi.api.format(tenant_id=tenant_id)
    LOG.info("Fetching status for tenant_id=%s from %s", tenant_id, url)
    headers = {"Authorization": "Bearer %s" % token} if token else {}
    try:
        async with retrying_request(lambda: session.get(url, headers=headers)) as response:
            response.raise_for_status()
            body = await response.json()
            print(json.dumps(body, indent=2))
    except aiohttp.ClientError as exc:
        LOG.error("Failed to fetch status from statusapi: %s", exc)
