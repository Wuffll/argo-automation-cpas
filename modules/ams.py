import asyncio
import json
import logging

from argo_ams_library.amsexceptions import AmsException

LOG = logging.getLogger(__name__)


async def pull_message(ams, settings):
    subscription = settings.ams.subscription
    LOG.info("Pulling message from AMS subscription %s", subscription)
    try:
        msgs = await asyncio.to_thread(ams.pullack, subscription, num=settings.ams.pullmsgs)
    except AmsException as exc:
        LOG.error("Failed to pull from AMS subscription %s: %s", subscription, exc)
        return None

    if not msgs:
        LOG.info("No messages in AMS subscription %s", subscription)
        return None

    try:
        payload = json.loads(msgs[0].get_data())
    except Exception as exc:
        LOG.error("Failed to decode AMS message payload: %s", exc)
        return None

    if "tenant_name" not in payload or "tenant_id" not in payload:
        LOG.error("AMS message missing required fields tenant_name/tenant_id: %s", payload)
        return None

    return payload


async def pull_and_print(ams, settings):
    subscription = settings.ams.subscription
    LOG.info("Pulling message from AMS subscription %s", subscription)
    try:
        msgs = await asyncio.to_thread(ams.pull_sub, subscription, num=settings.ams.pullmsgs)
    except AmsException as exc:
        LOG.error("Failed to pull from AMS subscription %s: %s", subscription, exc)
        return

    if not msgs:
        print("No messages in AMS subscription %s" % subscription)
        return

    for _, msg in msgs:
        raw = msg.get_data()
        try:
            payload = json.loads(raw)
            print(json.dumps(payload, indent=2))
        except Exception:
            print(raw)
