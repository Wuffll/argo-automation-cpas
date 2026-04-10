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


def _decode_message(msg):
    # pullack returns [msg, ...]; pull_sub returns [(ack_id, msg), ...]
    if isinstance(msg, tuple):
        msg = msg[1]
    try:
        return json.loads(msg.get_data())
    except Exception as exc:
        LOG.error("Failed to decode AMS message payload: %s", exc)
        return None


def _matches_filter(payload, settings):
    props = payload.get("properties") or {}
    tenant_name = props.get("tenant_name")
    tenant_id = props.get("tenant_id")
    if not tenant_name or not tenant_id:
        LOG.warning("Skipping AMS message missing properties.tenant_name/tenant_id: %s", payload)
        return False
    tenants = settings.automation.tenants
    if tenants and tenant_name not in tenants:
        LOG.info("Skipping AMS message for tenant_name=%s (not in automation.tenants)",
                 tenant_name)
        return False
    events = settings.ams.events
    name = payload.get("name")
    if events and name not in events:
        LOG.info("Skipping AMS message for tenant_name=%s name=%s (not in ams.events)",
                 tenant_name, name)
        return False
    return True


async def pull_messages(ams, settings):
    subscription = settings.ams.subscription
    method = ams.pullack if settings.ams.ack else ams.pull_sub
    LOG.info("Pulling messages from AMS subscription %s (ack=%s)", subscription, settings.ams.ack)
    try:
        msgs = await asyncio.to_thread(method, subscription, num=settings.ams.pullmsgs)
    except AmsException as exc:
        LOG.error("Failed to pull from AMS subscription %s: %s", subscription, exc)
        return []

    if not msgs:
        LOG.info("No messages in AMS subscription %s", subscription)
        return []

    matched = []
    for item in msgs:
        payload = _decode_message(item)
        if payload is None:
            continue
        if _matches_filter(payload, settings):
            matched.append(payload)

    LOG.info("Pulled %d message(s), %d matched tenant/event filter", len(msgs), len(matched))
    return matched


async def pull_and_print(ams, settings, filter_events=False):
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

    printed = 0
    for item in msgs:
        msg = item[1] if isinstance(item, tuple) else item
        raw = msg.get_data()
        try:
            payload = json.loads(raw)
        except Exception:
            if not filter_events:
                print(raw)
            continue
        if filter_events and not _matches_filter(payload, settings):
            continue
        print(json.dumps(payload, indent=2))
        printed += 1

    if filter_events and printed == 0:
        print("No messages matching tenant/event filter in AMS subscription %s" % subscription)
