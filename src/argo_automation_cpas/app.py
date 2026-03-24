import asyncio
import logging

import aiohttp
import ansible_runner

from argo_automation_cpas.messaging import init_ams


LOG = logging.getLogger(__name__)


class Application:
    def __init__(self, settings):
        self.settings = settings

    async def run(self):
        ams = await asyncio.to_thread(init_ams, self.settings)

        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)

        async with (
            aiohttp.ClientSession(
                base_url=self.settings.webapi.url,
                timeout=timeout,
                connector=aiohttp.TCPConnector(ssl=self.settings.verify_ssl),
            ) as webapi_session,
            aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(ssl=self.settings.verify_ssl),
            ) as iam_session,
        ):
            await self._probe_webapi(webapi_session)
            token = await self._fetch_iam_token(iam_session)
            await self._run_ansible()

    async def _probe_webapi(self, session):
        LOG.info("Probing Web API endpoint %s", self.settings.webapi.url)

        try:
            async with session.get("/") as response:
                LOG.info("Received probe status %s", response.status)
        except aiohttp.ClientError as exc:
            LOG.warning("Web API probe failed: %s", exc)

    async def _fetch_iam_token(self, session):
        LOG.info("Fetching OIDC token from IAM %s", self.settings.iam.host)

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.settings.iam.oidc_client_id,
            "client_secret": self.settings.iam.oidc_client_secret,
        }

        try:
            async with session.post(self.settings.iam.host, data=payload) as response:
                response.raise_for_status()
                data = await response.json()
                LOG.info(
                    "IAM token obtained (expires_in=%s)", data.get("expires_in", "unknown")
                )
                return data["access_token"]
        except aiohttp.ClientError as exc:
            LOG.warning("IAM token request failed: %s", exc)
            return None

    async def _run_ansible(self):
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s",
            self.settings.ansible_private_data_dir,
            self.settings.ansible_playbook,
        )

        runner = await asyncio.to_thread(
            ansible_runner.run,
            private_data_dir=self.settings.ansible_private_data_dir,
            playbook=self.settings.ansible_playbook,
            quiet=True,
        )

        status = getattr(runner, "status", "unknown")
        rc = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)
