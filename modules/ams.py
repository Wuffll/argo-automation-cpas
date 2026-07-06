import json
import logging

from argo_ams_library import ArgoMessagingService
from argo_ams_library.amsexceptions import AmsException, AmsServiceException

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.tokens import ComponentTokens

LOG = logging.getLogger(__name__)


class AMS:
    def __init__(self):
        self.settings = get_settings()
        self.tokens = ComponentTokens("ams")

        ams = ArgoMessagingService(
            endpoint=self.settings.ams.host,
            token=self.settings.ams.token,
            project=self.settings.ams.project,
        )

        LOG.info(
            "Initialised AMS client for project=%s host=%s subscription=%s",
            self.settings.ams.project,
            self.settings.ams.host,
            self.settings.ams.subscription,
        )

        try:
            sub_exists = ams.has_sub(self.settings.ams.subscription)
        except AmsServiceException as exc:
            LOG.error(
                "AMS request failed for project=%s host=%s: %s (HTTP %s)",
                self.settings.ams.project,
                self.settings.ams.host,
                exc.msg,
                exc.code,
            )
            raise SystemExit(1)

        if not sub_exists:
            LOG.error(
                "Subscription %r does not exist in project %r",
                self.settings.ams.subscription,
                self.settings.ams.project,
            )
            raise SystemExit(1)

        LOG.info("Subscription %r confirmed", self.settings.ams.subscription)

        self._ams = ams

    def move_offset(self, delta):
        sub = self.settings.ams.subscription
        offsets = self._ams.getoffsets_sub(sub)
        current = offsets["current"]
        n = int(delta)
        new_offset = max(offsets["min"], min(offsets["max"], current + n))
        self._ams.modifyoffset_sub(sub, new_offset)
        LOG.info(
            "Moved subscription %s offset from %d to %d (%+d)",
            sub,
            current,
            new_offset,
            n,
        )

    def _decode_message(self, msg):
        if isinstance(msg, tuple):
            msg = msg[1]
        try:
            return json.loads(msg.get_data())
        except Exception as exc:
            LOG.error("Failed to decode AMS message payload: %s", exc)
            return None

    def _matches_filter(self, payload):
        props = payload.get("properties") or {}
        tenant_name = props.get("tenant_name")
        tenant_id = props.get("tenant_id")
        if not tenant_name or not tenant_id:
            LOG.warning(
                "AMS message missing properties.tenant_name/tenant_id: %s", payload
            )
            return False
        tenants = self.settings.automation.tenants
        if tenants and tenant_name not in tenants:
            return False
        events = self.settings.ams.events
        name = payload.get("name")
        if events and name not in events:
            LOG.info(
                "Skipping AMS message for tenant_name=%s name=%s (not in ams.events)",
                tenant_name,
                name,
            )
            return False
        return True

    def pull_messages(self):
        subscription = self.settings.ams.subscription
        method = self._ams.pullack_sub if self.settings.ams.ack else self._ams.pull_sub
        LOG.info(
            "Pulling messages from AMS subscription %s (ack=%s)",
            subscription,
            self.settings.ams.ack,
        )
        try:
            msgs = method(
                subscription,
                num=self.settings.ams.pullmsgs,
                return_immediately=self.settings.ams.return_immediately,
            )
        except AmsException as exc:
            LOG.error("Failed to pull from AMS subscription %s: %s", subscription, exc)
            return []

        if not msgs:
            LOG.info("No messages in AMS subscription %s", subscription)
            return []

        matched = []
        for item in msgs:
            payload = self._decode_message(item)
            if payload is None:
                continue
            if self._matches_filter(payload):
                matched.append(payload)

        LOG.info(
            "Pulled %d message(s), %d matched tenant/event filter",
            len(msgs),
            len(matched),
        )
        return matched

    def pull_and_print(self, filter_events=False):
        subscription = self.settings.ams.subscription
        LOG.info("Pulling message from AMS subscription %s (no ack)", subscription)
        try:
            msgs = self._ams.pull_sub(
                subscription,
                num=self.settings.ams.pullmsgs,
                return_immediately=self.settings.ams.return_immediately,
            )
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
            if filter_events and not self._matches_filter(payload):
                continue
            print(json.dumps(payload, indent=2))
            printed += 1

        if filter_events and printed == 0:
            print(
                "No messages matching tenant/event filter in AMS subscription %s"
                % subscription
            )
