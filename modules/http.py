import asyncio
import logging

import aiohttp

from argo_automation_cpas.config import get_settings

LOG = logging.getLogger(__name__)

DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0


class SessionWithRetry:
    def __init__(self, base_url=None):
        settings = get_settings()
        timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
        kwargs = dict(
            timeout=timeout,
            connector=aiohttp.TCPConnector(ssl=settings.verify_ssl),
        )
        if base_url:
            kwargs["base_url"] = base_url
        self.session = aiohttp.ClientSession(**kwargs)
        self.retries = DEFAULT_RETRIES
        self.retry_delay = DEFAULT_RETRY_DELAY

    async def _request(self, method, url, **kwargs):
        method_obj = getattr(self.session, method)
        last_exc = None

        for attempt in range(self.retries):
            try:
                async with method_obj(url, **kwargs) as response:
                    response.raise_for_status()
                    if response.content_type == "application/json":
                        body = await response.json()
                    else:
                        body = await response.text()
                    return body
            except aiohttp.ClientConnectionError as exc:
                last_exc = exc
                if attempt < self.retries - 1:
                    wait = self.retry_delay * (attempt + 1)
                    LOG.warning(
                        "Socket error (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, self.retries, exc, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    LOG.warning(
                        "Socket error (attempt %d/%d): %s — giving up",
                        attempt + 1, self.retries, exc,
                    )
        raise last_exc

    async def http_get(self, url, headers=None):
        return await self._request("get", url, headers=headers or {})

    async def http_post(self, url, headers=None, data=None, json=None):
        kwargs = {"headers": headers or {}}
        if data is not None:
            kwargs["data"] = data
        if json is not None:
            kwargs["json"] = json
        return await self._request("post", url, **kwargs)

    async def http_patch(self, url, headers=None, json=None):
        kwargs = {"headers": headers or {}}
        if json is not None:
            kwargs["json"] = json
        return await self._request("patch", url, **kwargs)

    async def close(self):
        await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
