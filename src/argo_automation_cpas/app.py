from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import ansible_runner

from .config import Settings

LOG = logging.getLogger(__name__)


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
        connector = aiohttp.TCPConnector(ssl=self.settings.verify_ssl)

        async with aiohttp.ClientSession(
            base_url=self.settings.base_url,
            timeout=timeout,
            connector=connector,
        ) as session:
            await self._probe(session)
            await self._run_ansible()

    async def _probe(self, session: aiohttp.ClientSession) -> None:
        LOG.info("Probing AMS endpoint %s", self.settings.base_url)

        try:
            async with session.get("/") as response:
                LOG.info("Received probe status %s", response.status)
        except aiohttp.ClientError as exc:
            LOG.warning("Endpoint probe failed: %s", exc)

        await self._touch_ams_library()

    async def _touch_ams_library(self) -> None:
        # The dependency is imported lazily because the exact public API will
        # depend on the AMS version you target next.
        try:
            __import__("argo_ams_library")
            LOG.info("argo-ams-library import succeeded")
        except ImportError:
            LOG.warning("argo-ams-library is not installed or exposes a different import path")

    async def _run_ansible(self) -> None:
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

        status: Any = getattr(runner, "status", "unknown")
        rc: Any = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)
