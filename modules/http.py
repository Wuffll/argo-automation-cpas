import aiohttp


def client_session(settings, base_url=None):
    timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
    kwargs = dict(
        timeout=timeout,
        connector=aiohttp.TCPConnector(ssl=settings.verify_ssl),
    )
    if base_url:
        kwargs["base_url"] = base_url
    return aiohttp.ClientSession(**kwargs)
