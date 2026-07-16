import json
import logging
from datetime import datetime, timezone

import aiohttp

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.http import SessionWithRetry

LOG = logging.getLogger(__name__)

JOB_PICKED_UP_MESSAGE = "Event picked up by argo-automation-cpas"


class StatusAPI:
    def __init__(self):
        self.settings = get_settings()

    def _url(self, tenant_id):
        return self.settings.statusapi.api.format(tenant_id=tenant_id)

    def _auth_headers(self, token):
        return {"Authorization": "Bearer %s" % token} if token else {}

    async def report_status(self, tenant_id, status, token):
        url = self._url(tenant_id)
        LOG.info("Reporting status=%s for tenant_id=%s to %s", status, tenant_id, url)
        headers = self._auth_headers(token)
        try:
            async with SessionWithRetry() as session:
                await session.http_patch(url, json={"status": status}, headers=headers)
                LOG.info("Status reported: tenant_id=%s status=%s", tenant_id, status)
        except aiohttp.ClientError as exc:
            LOG.warning("Failed to report status to statusapi: %s", exc)

    async def update_job_status(self, tenant_id, event, status, token,
                                message=JOB_PICKED_UP_MESSAGE):
        url = self._url(tenant_id)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        body = {
            "jobs": [
                {
                    "name": event,
                    "status": status,
                    "end": now,
                    "message": message,
                }
            ]
        }
        LOG.info("Updating job status tenant_id=%s event=%s status=%s at %s",
                 tenant_id, event, status, url)
        headers = self._auth_headers(token)
        headers.update({"Content-Type": "application/json"})

        try:
            async with SessionWithRetry() as session:
                await session.http_patch(url, json=body, headers=headers)
                LOG.info("Job status updated: tenant_id=%s event=%s status=%s",
                         tenant_id, event, status)
        except aiohttp.ClientError as exc:
            LOG.warning("Failed to update job status: %s", exc)

    async def get_job_status(self, tenant_id, event, token):
        url = self._url(tenant_id)
        headers = self._auth_headers(token)
        headers.update({"Accept": "application/json"})

        try:
            async with SessionWithRetry() as session:
                body = await session.http_get(url, headers=headers)
        except aiohttp.ClientError as exc:
            LOG.warning("Failed to fetch status for tenant_id=%s: %s", tenant_id, exc)
            return None

        jobs = (body.get("status") or {}).get("jobs") or []
        for job in jobs:
            if job.get("name") == event:
                return job.get("status")
        return None

    async def fetch_status(self, tenant_id, token):
        url = self._url(tenant_id)

        LOG.info("Fetching status for tenant_id=%s from %s", tenant_id, url)
        headers = self._auth_headers(token)
        headers.update({"Accept": "application/json"})
        try:
            async with SessionWithRetry() as session:
                body = await session.http_get(url, headers=headers)
                print(json.dumps(body, indent=2))
        except aiohttp.ClientError as exc:
            LOG.error("Failed to fetch status from statusapi: %s", exc)
