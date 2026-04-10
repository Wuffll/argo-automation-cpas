import asyncio
import json
import logging

from argo_ams_library import ArgoMessagingService
from argo_ams_library.amsexceptions import AmsException, AmsServiceException

LOG = logging.getLogger(__name__)


def init_ams(settings):
    """Initialise and return an ArgoMessagingService instance.

    Uses settings.ams.host, settings.ams.token and settings.ams.project
    from the loaded configuration. Exits with status 1 on any AMS error.

    Args:
        settings: Settings object returned by config.get_settings().

    Returns:
        ArgoMessagingService instance ready for use.
    """
    ams = ArgoMessagingService(
        endpoint=settings.ams.host,
        token=settings.ams.token,
        project=settings.ams.project,
    )

    LOG.info(
        "Initialised AMS client for project=%s host=%s subscription=%s",
        settings.ams.project,
        settings.ams.host,
        settings.ams.subscription,
    )

    try:
        sub_exists = ams.has_sub(settings.ams.subscription)
    except AmsServiceException as exc:
        LOG.error(
            "AMS request failed for project=%s host=%s: %s (HTTP %s)",
            settings.ams.project,
            settings.ams.host,
            exc.msg,
            exc.code,
        )
        raise SystemExit(1)

    if not sub_exists:
        LOG.error(
            "Subscription %r does not exist in project %r",
            settings.ams.subscription,
            settings.ams.project,
        )
        raise SystemExit(1)

    LOG.info("Subscription %r confirmed", settings.ams.subscription)

    return ams


async def pull_message(ams, settings):
    subscription = settings.ams.subscription
    method = ams.pullack if settings.ams.ack else ams.pull_sub
    LOG.info("Pulling message from AMS subscription %s (ack=%s)", subscription, settings.ams.ack)
    try:
        msgs = await asyncio.to_thread(method, subscription, num=settings.ams.pullmsgs)
    except AmsException as exc:
        LOG.error("Failed to pull from AMS subscription %s: %s", subscription, exc)
        return None

    if not msgs:
        LOG.info("No messages in AMS subscription %s", subscription)
        return None

    # pullack returns [msg, ...]; pull_sub returns [(ack_id, msg), ...]
    first = msgs[0]
    if isinstance(first, tuple):
        first = first[1]

    try:
        payload = json.loads(first.get_data())
    except Exception as exc:
        LOG.error("Failed to decode AMS message payload: %s", exc)
        return None

    if "tenant_name" not in payload or "tenant_id" not in payload:
        LOG.error("AMS message missing required fields tenant_name/tenant_id: %s", payload)
        return None

    return payload


async def pull_and_print(ams, settings):
    subscription = settings.ams.subscription
    method = ams.pullack if settings.ams.ack else ams.pull_sub
    LOG.info("Pulling message from AMS subscription %s (ack=%s)", subscription, settings.ams.ack)
    try:
        msgs = await asyncio.to_thread(method, subscription, num=settings.ams.pullmsgs)
    except AmsException as exc:
        LOG.error("Failed to pull from AMS subscription %s: %s", subscription, exc)
        return

    if not msgs:
        print("No messages in AMS subscription %s" % subscription)
        return

    for item in msgs:
        # pullack returns [msg, ...]; pull_sub returns [(ack_id, msg), ...]
        msg = item[1] if isinstance(item, tuple) else item
        raw = msg.get_data()
        try:
            payload = json.loads(raw)
            print(json.dumps(payload, indent=2))
        except Exception:
            print(raw)
