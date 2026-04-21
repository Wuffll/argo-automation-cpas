import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

from argo_automation_cpas.app import Application

from conftest import prime_settings


@pytest.fixture
def settings():
    return prime_settings(SimpleNamespace(
        ansible_private_data_dir="/tmp/ansible",
        ansible_playbook="init.yml",
        general=SimpleNamespace(
            request_timeout=30.0,
            verify_ssl=True,
            retries=3,
            retry_delay=1.0,
        ),
        automation=SimpleNamespace(
            tenants=["TENANT-A"],
        ),
        ansible=SimpleNamespace(
            ssh_private_key="/home/user/.ssh/sshkey",
            user_connector="user",
            group_connector="group",
            defaults={
                "connector_tenant_topo_type": "CSV",
                "connector_tenant_cron_weights_disable": True,
            },
            tokens={"TENANT-A": "tok-a"},
            connectors_playbook="connectors.yml",
            connectors_inventory="connectors.ini",
        ),
        webapi=SimpleNamespace(
            host="api.devel.mon.argo.grnet.gr",
            url="https://api.devel.mon.argo.grnet.gr",
            url_api_config="/api/v2/feeds/topology",
            url_api_integrations="/api/v3/integrations/components/{component}/by-tenant-name/{tenant_name}/refresh",
            token_component_admin="admin-tok",
            components=["connectors", "sensu"],
            tokens_spool="/tmp/webapi_tokens.json",
        ),
        iam=SimpleNamespace(
            api="https://login-devel.einfra.grnet.gr/auth/realms/einfra/protocol/openid-connect/token",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
            token_spool="/tmp/iam_access_test.yml",
        ),
        ams=SimpleNamespace(
            host="api.devel.msg.argo.grnet.gr",
            token="test-token",
            project="TEST-PROJECT",
            subscription="events-sub-1",
            pullmsgs=1,
            ack=False,
            return_immediately=True,
            events=["INIT_TOPOLOGY_CONNECTOR"],
        ),
        statusapi=SimpleNamespace(
            api="https://api-status.devel.mon.argo.grnet.gr/v1/automation/tenants/{tenant_id}/status",
        ),
    ))


# ---------------------------------------------------------------------------
# run: --clean-artifacts
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.clean_artifacts")
async def test_run_clean_artifacts(mock_clean, settings):
    app = Application(clean_artifacts=[])
    await app.run()
    mock_clean.assert_called_once_with("/tmp/ansible/artifacts", [])


@patch("argo_automation_cpas.app.clean_artifacts")
async def test_run_clean_artifacts_with_roles(mock_clean, settings):
    app = Application(clean_artifacts=["connector"])
    await app.run()
    mock_clean.assert_called_once_with("/tmp/ansible/artifacts", ["connector"])


# ---------------------------------------------------------------------------
# run: --only-ansible
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.Ansible")
async def test_run_only_ansible(mock_ansible_cls, settings):
    mock_ansible = MagicMock()
    mock_ansible.run = AsyncMock()
    mock_ansible_cls.return_value = mock_ansible

    app = Application(only_ansible="connectors.yml", inventory="hosts.ini",
                      add_tenants=["egi"], remove_tenants=["eudat"], show_artifacts=[])
    await app.run()

    mock_ansible_cls.assert_called_once_with()
    mock_ansible.run.assert_called_once_with(
        "connectors.yml",
        inventory="hosts.ini",
        add_tenants=["egi"],
        remove_tenants=["eudat"],
        show_artifacts=[],
    )


# ---------------------------------------------------------------------------
# run: --only-webapi
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.WebAPI")
async def test_run_only_webapi(mock_webapi_cls, settings):
    mock_webapi = MagicMock()
    mock_webapi.run = AsyncMock()
    mock_webapi_cls.return_value = mock_webapi

    app = Application(only_webapi=True)
    await app.run()

    mock_webapi_cls.assert_called_once_with()
    mock_webapi.run.assert_called_once()


# ---------------------------------------------------------------------------
# run: --only-iam
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.IAM")
async def test_run_only_iam(mock_iam_cls, settings, capsys):
    mock_iam = MagicMock()
    mock_iam.fetch_token = AsyncMock(return_value="iam-token-123")
    mock_iam.close = AsyncMock()
    mock_iam_cls.return_value = mock_iam

    app = Application(only_iam=True)
    await app.run()

    mock_iam.fetch_token.assert_called_once()
    mock_iam.close.assert_called_once()
    assert "iam-token-123" in capsys.readouterr().out


@patch("argo_automation_cpas.app.IAM")
async def test_run_only_iam_no_token(mock_iam_cls, settings, capsys):
    mock_iam = MagicMock()
    mock_iam.fetch_token = AsyncMock(return_value=None)
    mock_iam.close = AsyncMock()
    mock_iam_cls.return_value = mock_iam

    app = Application(only_iam=True)
    await app.run()

    assert capsys.readouterr().out == ""
    mock_iam.close.assert_called_once()


# ---------------------------------------------------------------------------
# run: --only-statusapi
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.StatusAPI")
@patch("argo_automation_cpas.app.IAM")
async def test_run_only_statusapi(mock_iam_cls, mock_statusapi_cls, settings):
    mock_iam = MagicMock()
    mock_iam.fetch_token = AsyncMock(return_value="iam-tok")
    mock_iam.close = AsyncMock()
    mock_iam_cls.return_value = mock_iam

    mock_statusapi = MagicMock()
    mock_statusapi.fetch_status = AsyncMock()
    mock_statusapi.close = AsyncMock()
    mock_statusapi_cls.return_value = mock_statusapi

    app = Application(only_statusapi="tenant-abc")
    await app.run()

    mock_iam.fetch_token.assert_called_once()
    mock_statusapi.fetch_status.assert_called_once_with("tenant-abc", "iam-tok")
    mock_iam.close.assert_called_once()
    mock_statusapi.close.assert_called_once()


# ---------------------------------------------------------------------------
# run: --only-ams
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.AMS")
@patch("argo_automation_cpas.app.asyncio")
async def test_run_only_ams(mock_asyncio, mock_ams_cls, settings):
    mock_ams_instance = MagicMock()
    mock_ams_instance.pull_and_print = AsyncMock()

    mock_ams = MagicMock()
    mock_ams.init.return_value = mock_ams_instance
    mock_ams_cls.return_value = mock_ams

    mock_asyncio.to_thread = AsyncMock(return_value=mock_ams_instance)

    app = Application(only_ams=True)
    await app.run()

    mock_ams_instance.pull_and_print.assert_called_once_with(filter_events=False)


# ---------------------------------------------------------------------------
# run: full flow
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.Ansible")
@patch("argo_automation_cpas.app.WebAPI")
@patch("argo_automation_cpas.app.StatusAPI")
@patch("argo_automation_cpas.app.IAM")
@patch("argo_automation_cpas.app.AMS")
@patch("argo_automation_cpas.app.asyncio")
async def test_run_full_flow(
    mock_asyncio,
    mock_ams_cls, mock_iam_cls, mock_statusapi_cls, mock_webapi_cls, mock_ansible_cls,
    settings,
):
    mock_ams_instance = MagicMock()
    mock_ams_instance.pull_messages = AsyncMock(return_value=[{
        "name": "INIT_TOPOLOGY_CONNECTOR",
        "properties": {"tenant_name": "EGI", "tenant_id": "tid-1"},
    }])
    mock_ams = MagicMock()
    mock_ams.init.return_value = mock_ams_instance
    mock_ams_cls.return_value = mock_ams
    mock_asyncio.to_thread = AsyncMock(return_value=mock_ams_instance)

    mock_iam = MagicMock()
    mock_iam.fetch_token = AsyncMock(return_value="iam-tok")
    mock_iam.close = AsyncMock()
    mock_iam_cls.return_value = mock_iam

    mock_webapi = MagicMock()
    mock_webapi.refresh_tokens = AsyncMock(return_value={"EGI": {"connectors": "conn-tok"}})
    mock_webapi.find_connector_token.return_value = "conn-tok"
    mock_webapi.fetch_topology_config = AsyncMock(return_value={"connector_tenant_topo_type": "GOCDB"})
    mock_webapi.close = AsyncMock()
    mock_webapi_cls.return_value = mock_webapi

    mock_statusapi = MagicMock()
    mock_statusapi.get_job_status = AsyncMock(return_value="INITIALISED")
    mock_statusapi.update_job_status = AsyncMock()
    mock_statusapi.close = AsyncMock()
    mock_statusapi_cls.return_value = mock_statusapi

    mock_ansible = MagicMock()
    mock_ansible.run = AsyncMock(return_value=True)
    mock_ansible_cls.return_value = mock_ansible

    app = Application()
    await app.run()

    mock_iam.fetch_token.assert_called_once()
    mock_webapi.refresh_tokens.assert_called_once()
    mock_statusapi.get_job_status.assert_called_once_with(
        "tid-1", "INIT_TOPOLOGY_CONNECTOR", "iam-tok"
    )
    assert mock_statusapi.update_job_status.call_count == 2
    mock_ansible.run.assert_called_once()
    mock_webapi.close.assert_called_once()
    mock_iam.close.assert_called_once()
    mock_statusapi.close.assert_called_once()


@patch("argo_automation_cpas.app.AMS")
@patch("argo_automation_cpas.app.asyncio")
async def test_run_full_flow_no_ams_message(mock_asyncio, mock_ams_cls, settings):
    mock_ams_instance = MagicMock()
    mock_ams_instance.pull_messages = AsyncMock(return_value=[])
    mock_ams = MagicMock()
    mock_ams.init.return_value = mock_ams_instance
    mock_ams_cls.return_value = mock_ams
    mock_asyncio.to_thread = AsyncMock(return_value=mock_ams_instance)

    app = Application()
    await app.run()

    mock_ams_instance.pull_messages.assert_called_once()
