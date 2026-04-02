import asyncio
import json
import logging
import os
import re
import shutil
import time

import aiohttp
import ansible_runner
import yaml

from argo_ams_library.amsexceptions import AmsException
from argo_automation_cpas.http import client_session
from argo_automation_cpas.messaging import init_ams


LOG = logging.getLogger(__name__)


class Application:
    def __init__(self, settings, only_ansible=None, only_ams=False, only_webapi=False, only_iam=False, only_statusapi=None, inventory=None,
                 show_artifacts=None, clean_artifacts=None,
                 add_tenants=None, remove_tenants=None):
        self.settings = settings
        self.only_ansible = only_ansible  # None or playbook filename string
        self.only_ams = only_ams          # True = pull AMS message, print and exit
        self.only_webapi = only_webapi    # True = probe + fetch topology config and exit
        self.only_iam = only_iam          # True = fetch IAM token, print and exit
        self.only_statusapi = only_statusapi  # None or [tenant_id, status]
        self.inventory = inventory  # None or path to inventory file/directory
        self.show_artifacts = show_artifacts  # None=off, []=all, ['role1',...]=filtered
        self.clean_artifacts = clean_artifacts  # None=off, []=all, ['role1',...]=filtered
        self.add_tenants = add_tenants  # None or list of tenant names
        self.remove_tenants = remove_tenants  # None or list of tenant names
        self._webapi_overrides = {}  # connector_tenant_* overrides from webapi

    async def run(self):
        if self.clean_artifacts is not None:
            self._clean_artifacts(self.clean_artifacts)
            return

        if self.only_ansible is not None:
            await self._run_ansible(self.only_ansible)
            return

        if self.only_webapi:
            await self._run_only_webapi()
            return

        if self.only_iam:
            await self._run_only_iam()
            return

        if self.only_statusapi is not None:
            await self._run_only_statusapi(self.only_statusapi)
            return

        ams = await asyncio.to_thread(init_ams, self.settings)

        if self.only_ams:
            await self._pull_and_print_ams(ams)
            return

        payload = await self._pull_ams_message(ams)
        if payload is None:
            return

        tenant_name = payload["tenant_name"]
        tenant_id = payload["tenant_id"]
        LOG.info("Processing tenant_name=%s tenant_id=%s", tenant_name, tenant_id)

        async with (
            client_session(self.settings, base_url=self.settings.webapi.url) as webapi_session,
            client_session(self.settings) as iam_session,
            client_session(self.settings) as statusapi_session,
        ):
            await self._probe_webapi(webapi_session)
            token = await self._fetch_iam_token(iam_session)
            await self._report_status(statusapi_session, tenant_id, "IN_PROGRESS", token)
            self._webapi_overrides = await self._fetch_topology_config(webapi_session)
            await self._run_ansible(self.settings.ansible_playbook)

    def _clean_artifacts(self, roles):
        artifacts_dir = os.path.join(self.settings.ansible_private_data_dir, "artifacts")

        if not os.path.isdir(artifacts_dir):
            LOG.info("Artifacts directory does not exist: %s", artifacts_dir)
            return

        if not roles:
            shutil.rmtree(artifacts_dir)
            os.makedirs(artifacts_dir)
            LOG.info("Removed all artifacts from %s", artifacts_dir)
            return

        roles_set = set(roles)
        removed = 0

        for entry in os.scandir(artifacts_dir):
            if not entry.is_dir():
                continue

            stdout_path = os.path.join(entry.path, "stdout")
            try:
                with open(stdout_path) as fh:
                    content = fh.read()
            except OSError:
                continue

            if any(
                re.search(r"TASK \[" + re.escape(role) + r" : ", content)
                for role in roles_set
            ):
                shutil.rmtree(entry.path)
                LOG.info("Removed artifact run %s", entry.name)
                removed += 1

        LOG.info(
            "Removed %d artifact run(s) matching role(s): %s",
            removed, ", ".join(sorted(roles_set)),
        )

    _TASK_RE = re.compile(r"^TASK \[(?P<role>[^\]]+?) : [^\]]+\]")

    def _role_of(self, line):
        """Return the role name from a TASK line, or None if not a role task."""
        m = self._TASK_RE.match(line)
        return m.group("role").strip() if m else None

    def _filter_stdout(self, content, roles):
        """Filter stdout lines to tasks belonging to any of *roles*.

        PLAY headers and PLAY RECAP are always kept. When *roles* is empty
        (no filter requested) the full content is returned unchanged.
        """
        if not roles:
            return content

        width = 72
        result = []
        include_block = False

        for line in content.splitlines():
            if line.startswith("PLAY [") or line.startswith("PLAY RECAP"):
                include_block = False
                result.append(line)
            elif line.startswith("TASK ["):
                role = self._role_of(line)
                include_block = role in roles
                if include_block:
                    if result and result[-1] != "":
                        result.append("")
                    result.append(line)
            elif include_block:
                result.append(line)

        return "\n".join(result)

    def _print_artifacts(self, runner):
        roles = self.show_artifacts  # [] = all, ['r1', 'r2'] = filtered
        width = 72

        try:
            stdout = runner.stdout.read().strip()
        except Exception:
            stdout = ""

        try:
            stderr = runner.stderr.read().strip()
        except Exception:
            stderr = ""

        stdout = self._filter_stdout(stdout, roles)

        for label, content in (("STDOUT", stdout), ("STDERR", stderr)):
            print("\n" + "=" * width)
            if roles and label == "STDOUT":
                print(f"  {label}  [roles: {', '.join(roles)}]")
            else:
                print(f"  {label}")
            print("=" * width)
            if content:
                for line in content.splitlines():
                    print(f"  {line}")
            else:
                print("  (empty)")

        print("=" * width + "\n")

    async def _pull_ams_message(self, ams):
        LOG.info(
            "Pulling message from AMS subscription %s", self.settings.ams.subscription
        )
        try:
            msgs = await asyncio.to_thread(
                ams.pullack, self.settings.ams.subscription, num=1
            )
        except AmsException as exc:
            LOG.error("Failed to pull from AMS subscription %s: %s",
                      self.settings.ams.subscription, exc)
            return None

        if not msgs:
            LOG.info("No messages in AMS subscription %s", self.settings.ams.subscription)
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

    async def _run_only_statusapi(self, tenant_id):
        async with (
            client_session(self.settings) as iam_session,
            client_session(self.settings) as statusapi_session,
        ):
            token = await self._fetch_iam_token(iam_session)
            url = self.settings.statusapi.api.format(tenant_id=tenant_id)
            LOG.info("Fetching status for tenant_id=%s from %s", tenant_id, url)
            headers = {"Authorization": "Bearer %s" % token} if token else {}
            try:
                async with statusapi_session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    body = await response.json()
                    print(json.dumps(body, indent=2))
            except aiohttp.ClientError as exc:
                LOG.error("Failed to fetch status from statusapi: %s", exc)

    async def _run_only_iam(self):
        async with client_session(self.settings) as session:
            token = await self._fetch_iam_token(session)
            if token:
                print(token)

    async def _run_only_webapi(self):
        async with client_session(self.settings, base_url=self.settings.webapi.url) as session:
            await self._probe_webapi(session)
            overrides = await self._fetch_topology_config(session)
            if overrides:
                print(json.dumps(overrides, indent=2))

    async def _pull_and_print_ams(self, ams):
        LOG.info(
            "Pulling message from AMS subscription %s", self.settings.ams.subscription
        )
        try:
            msgs = await asyncio.to_thread(
                ams.pull_sub, self.settings.ams.subscription, num=1
            )
        except AmsException as exc:
            LOG.error("Failed to pull from AMS subscription %s: %s",
                      self.settings.ams.subscription, exc)
            return

        if not msgs:
            print("No messages in AMS subscription %s" % self.settings.ams.subscription)
            return

        for id, msg in msgs:
            raw = msg.get_data()
            try:
                payload = json.loads(raw)
                print(json.dumps(payload, indent=2))
            except Exception:
                print(raw)

    async def _report_status(self, session, tenant_id, status, token):
        url = self.settings.statusapi.api.format(tenant_id=tenant_id)
        LOG.info("Reporting status=%s for tenant_id=%s to %s", status, tenant_id, url)
        headers = {"Authorization": "Bearer %s" % token} if token else {}
        try:
            async with session.patch(url, json={"status": status}, headers=headers) as response:
                response.raise_for_status()
                LOG.info("Status reported: tenant_id=%s status=%s", tenant_id, status)
        except aiohttp.ClientError as exc:
            LOG.warning("Failed to report status to statusapi: %s", exc)

    async def _fetch_topology_config(self, session):
        url = self.settings.webapi.url_api_config
        LOG.info("Fetching topology config from webapi %s", url)
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                body = await response.json()
        except aiohttp.ClientError as exc:
            LOG.warning("Failed to fetch topology config from webapi: %s", exc)
            return {}

        data = body.get("data", [])
        if not data:
            LOG.warning("Empty data in topology config response")
            return {}

        entry = data[0]
        overrides = {}
        if "type" in entry:
            overrides["connector_tenant_topo_type"] = entry["type"]
        if "feed_url" in entry:
            overrides["connector_tenant_topo_feed"] = entry["feed_url"]

        LOG.info(
            "Topology config: topo_type=%s topo_feed=%s",
            overrides.get("connector_tenant_topo_type", "n/a"),
            overrides.get("connector_tenant_topo_feed", "n/a"),
        )
        return overrides

    async def _probe_webapi(self, session):
        LOG.info("Probing Web API endpoint %s", self.settings.webapi.url)

        try:
            async with session.get("/") as response:
                LOG.info("Received probe status %s", response.status)
        except aiohttp.ClientError as exc:
            LOG.warning("Web API probe failed: %s", exc)

    def _load_cached_token(self):
        path = self.settings.iam.token_spool
        try:
            with open(path) as fh:
                data = yaml.safe_load(fh) or {}
            token = data.get("access_token", "")
            expires_at = float(data.get("expires_at", 0))
            if token and time.time() < expires_at - 30:
                LOG.info("Using cached IAM token from %s (expires in %.0fs)", path, expires_at - time.time())
                return token
        except (OSError, ValueError):
            pass
        return None

    def _save_token(self, token, expires_in):
        path = self.settings.iam.token_spool
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            yaml.dump({"access_token": token, "expires_at": time.time() + expires_in}, fh)
        LOG.info("IAM token saved to %s", path)

    async def _fetch_iam_token(self, session):
        cached = self._load_cached_token()
        if cached:
            return cached

        LOG.info("Fetching OIDC token from IAM %s", self.settings.iam.api)

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.settings.iam.oidc_client_id,
            "client_secret": self.settings.iam.oidc_client_secret,
        }

        try:
            async with session.post(self.settings.iam.api, data=payload) as response:
                response.raise_for_status()
                data = await response.json()
                token = data["access_token"]
                expires_in = data.get("expires_in", 3600)
                LOG.info("IAM token obtained (expires_in=%s)", expires_in)
                self._save_token(token, expires_in)
                return token
        except aiohttp.ClientError as exc:
            LOG.warning("IAM token request failed: %s", exc)
            return None

    async def _run_ansible(self, playbook):
        private_key = self.settings.ansible.ssh_private_key
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self.settings.ansible_private_data_dir,
            playbook,
            self.inventory or "default",
            private_key or "none",
        )

        defaults = self.settings.ansible.defaults

        # Keys prefixed with "connector_tenant_" become per-tenant defaults
        # e.g. connector_tenant_topo_type -> tenant_topo_type
        _PREFIX = "connector_"
        tenant_defaults = {
            k[len(_PREFIX):]: v
            for k, v in defaults.items()
            if k.startswith(_PREFIX + "tenant_")
        }

        # webapi overrides take precedence over roles-defaults.yml
        for k, v in self._webapi_overrides.items():
            if k.startswith(_PREFIX + "tenant_"):
                tenant_defaults[k[len(_PREFIX):]] = v

        extravars = {k: v for k, v in defaults.items() if not k.startswith(_PREFIX + "tenant_")}
        if self.settings.ansible.user_connector:
            extravars["user_connector"] = self.settings.ansible.user_connector
        if self.settings.ansible.group_connector:
            extravars["group_connector"] = self.settings.ansible.group_connector

        if self.add_tenants is not None:
            extravars["connector_tenants"] = [
                {"tenant_name": t.upper(), **tenant_defaults}
                for t in self.add_tenants
            ]
        if self.remove_tenants is not None:
            extravars["connector_remove_tenants"] = [t.upper() for t in self.remove_tenants]

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            playbook=playbook,
            quiet=True,
        )

        if self.settings.ansible.tokens:
            extravars["connector_tokens"] = self.settings.ansible.tokens

        if extravars:
            kwargs["extravars"] = extravars
        if self.inventory:
            kwargs["inventory"] = self.inventory
        if private_key:
            kwargs["cmdline"] = "--private-key %s" % private_key

        runner = await asyncio.to_thread(ansible_runner.run, **kwargs)

        status = getattr(runner, "status", "unknown")
        rc = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)

        if self.show_artifacts is not None:
            self._print_artifacts(runner)
