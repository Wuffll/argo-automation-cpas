import asyncio
import logging

import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts

LOG = logging.getLogger(__name__)


async def run(settings, playbook, inventory=None, webapi_overrides=None, component_tokens=None,
              add_tenants=None, remove_tenants=None, show_artifacts=None):
    private_key = settings.ansible.ssh_private_key
    LOG.info(
        "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
        settings.ansible_private_data_dir,
        playbook,
        inventory or "default",
        private_key or "none",
    )

    defaults = settings.ansible.defaults

    # Keys prefixed with "connector_tenant_" become per-tenant defaults
    # e.g. connector_tenant_topo_type -> tenant_topo_type
    _PREFIX = "connector_"
    tenant_defaults = {
        k[len(_PREFIX):]: v
        for k, v in defaults.items()
        if k.startswith(_PREFIX + "tenant_")
    }

    # webapi overrides take precedence over roles-defaults.yml
    for k, v in (webapi_overrides or {}).items():
        if k.startswith(_PREFIX + "tenant_"):
            tenant_defaults[k[len(_PREFIX):]] = v

    extravars = {k: v for k, v in defaults.items() if not k.startswith(_PREFIX + "tenant_")}
    if settings.ansible.user_connector:
        extravars["user_connector"] = settings.ansible.user_connector
    if settings.ansible.group_connector:
        extravars["group_connector"] = settings.ansible.group_connector

    if add_tenants is not None:
        extravars["connector_tenants"] = [
            {"tenant_name": t.upper(), **tenant_defaults}
            for t in add_tenants
        ]
    if remove_tenants is not None:
        extravars["connector_remove_tenants"] = [t.upper() for t in remove_tenants]

    connector_tokens = dict(settings.ansible.tokens) if settings.ansible.tokens else {}
    if component_tokens:
        for tenant_name, components in component_tokens.items():
            for component, token in components.items():
                if "connector" in component and token:
                    connector_tokens.setdefault(tenant_name, {})
                    connector_tokens[tenant_name]["webapi"] = token
    if connector_tokens:
        extravars["connector_tokens"] = connector_tokens

    kwargs = dict(
        private_data_dir=settings.ansible_private_data_dir,
        playbook=playbook,
        quiet=True,
    )

    if extravars:
        kwargs["extravars"] = extravars
    if inventory:
        kwargs["inventory"] = inventory
    if private_key:
        kwargs["cmdline"] = "--private-key %s" % private_key

    runner = await asyncio.to_thread(ansible_runner.run, **kwargs)

    status = getattr(runner, "status", "unknown")
    rc = getattr(runner, "rc", "unknown")
    LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)

    if show_artifacts is not None:
        print_artifacts(runner, show_artifacts)
