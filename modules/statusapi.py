import json
import logging

import aiohttp

from argo_automation_cpas.http import retrying_request

LOG = logging.getLogger(__name__)


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
