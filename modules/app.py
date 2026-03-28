import asyncio
import logging
import os
import re
import shutil

import aiohttp
import ansible_runner

from argo_automation_cpas.messaging import init_ams


LOG = logging.getLogger(__name__)


class Application:
    def __init__(self, settings, only_ansible=None, inventory=None,
                 show_artifacts=None, clean_artifacts=None,
                 add_tenants=None, remove_tenants=None):
        self.settings = settings
        self.only_ansible = only_ansible  # None or playbook filename string
        self.inventory = inventory  # None or path to inventory file/directory
        self.show_artifacts = show_artifacts  # None=off, []=all, ['role1',...]=filtered
        self.clean_artifacts = clean_artifacts  # None=off, []=all, ['role1',...]=filtered
        self.add_tenants = add_tenants  # None or list of tenant names
        self.remove_tenants = remove_tenants  # None or list of tenant names

    async def run(self):
        if self.clean_artifacts is not None:
            self._clean_artifacts(self.clean_artifacts)
            return

        if self.only_ansible is not None:
            await self._run_ansible(self.only_ansible)
            return

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

    async def _run_ansible(self, playbook):
        private_key = self.settings.ansible.ssh_private_key
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self.settings.ansible_private_data_dir,
            playbook,
            self.inventory or "default",
            private_key or "none",
        )

        extravars = dict(self.settings.ansible.defaults)
        if self.settings.ansible.user_connector:
            extravars["user_connector"] = self.settings.ansible.user_connector
        if self.settings.ansible.group_connector:
            extravars["group_connector"] = self.settings.ansible.group_connector

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            playbook=playbook,
            quiet=True,
        )

        extravars['connector_tenants'] = list()
        extravars['connector_remove_tenants'] = list()
        for tenant_name in self.add_tenants:
            extravars['connector_tenants'].append(
                {
                    'tenant_name': tenant_name.upper()
                }
            )

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
