import asyncio
import logging
from contextlib import asynccontextmanager

import aiohttp

LOG = logging.getLogger(__name__)

DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0


def client_session(settings, base_url=None):
    timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
    kwargs = dict(
        timeout=timeout,
        connector=aiohttp.TCPConnector(ssl=settings.verify_ssl),
    )
    if base_url:
        kwargs["base_url"] = base_url
    return aiohttp.ClientSession(**kwargs)


@asynccontextmanager
async def retrying_request(make_cm, *, retries=DEFAULT_RETRIES, delay=DEFAULT_RETRY_DELAY):
    """Async context manager that retries on socket-level errors.

    *make_cm* is a zero-argument callable that returns an aiohttp request
    context manager, e.g. ``lambda: session.get(url)``.  It is called again
    on each retry so a fresh context manager is created every attempt.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            async with make_cm() as response:
                yield response
                return
        except aiohttp.ClientConnectionError as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = delay * (attempt + 1)
                LOG.warning(
                    "Socket error (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, retries, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                LOG.warning("Socket error (attempt %d/%d): %s — giving up", attempt + 1, retries, exc)
    raise last_exc
