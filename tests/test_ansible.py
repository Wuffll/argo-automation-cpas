import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from argo_automation_cpas.ansible import Ansible

from conftest import prime_settings


@pytest.fixture
def settings():
    return prime_settings(SimpleNamespace(
        ansible_private_data_dir="/tmp/ansible",
        ansible=SimpleNamespace(
            ssh_private_key="/home/user/.ssh/sshkey",
            user_connector="user",
            group_connector="group",
            defaults={
                "connector_tenant_topo_type": "CSV",
                "connector_tenant_cron_weights_disable": True,
            },
            tokens={"TENANT-A": "tok-a"},
        ),
        webapi=SimpleNamespace(
            tokens_spool="/tmp/webapi_tokens.json",
        ),
    ))


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_basic(mock_asyncio, mock_print, settings):
    mock_runner = MagicMock(status="successful", rc=0)
    mock_asyncio.to_thread = AsyncMock(return_value=mock_runner)

    svc = Ansible()
    result = await svc.run("connectors.yml")

    mock_asyncio.to_thread.assert_called_once()
    _, kwargs = mock_asyncio.to_thread.call_args
    assert kwargs["playbook"] == "connectors.yml"
    assert kwargs["private_data_dir"] == "/tmp/ansible"
    assert kwargs["quiet"] is True
    assert "--private-key /home/user/.ssh/sshkey" in kwargs["cmdline"]
    mock_print.assert_not_called()
    assert result is True


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_with_add_tenants(mock_asyncio, mock_print, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock(status="successful", rc=0))

    svc = Ansible()
    await svc.run("connectors.yml", add_tenants=["egi", "eudat"])

    _, kwargs = mock_asyncio.to_thread.call_args
    extravars = kwargs["extravars"]
    tenants = extravars["connector_tenants"]
    assert len(tenants) == 2
    assert tenants[0]["tenant_name"] == "EGI"
    assert tenants[0]["tenant_topo_type"] == "CSV"
    assert tenants[0]["tenant_cron_weights_disable"] is True
    assert tenants[1]["tenant_name"] == "EUDAT"


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_with_remove_tenants(mock_asyncio, mock_print, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock(status="successful", rc=0))

    svc = Ansible()
    await svc.run("connectors.yml", remove_tenants=["egi"])

    _, kwargs = mock_asyncio.to_thread.call_args
    extravars = kwargs["extravars"]
    assert extravars["connector_remove_tenants"] == ["EGI"]


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_with_webapi_overrides(mock_asyncio, mock_print, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock(status="successful", rc=0))

    svc = Ansible()
    overrides = {"connector_tenant_topo_type": "GOCDB", "connector_tenant_topo_feed": "https://gocdb.example.com"}
    await svc.run("connectors.yml", add_tenants=["egi"], webapi_overrides=overrides)

    _, kwargs = mock_asyncio.to_thread.call_args
    tenants = kwargs["extravars"]["connector_tenants"]
    assert tenants[0]["tenant_topo_type"] == "GOCDB"
    assert tenants[0]["tenant_topo_feed"] == "https://gocdb.example.com"


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_with_inventory(mock_asyncio, mock_print, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock(status="successful", rc=0))

    svc = Ansible()
    await svc.run("connectors.yml", inventory="hosts.ini")

    _, kwargs = mock_asyncio.to_thread.call_args
    assert kwargs["inventory"] == "hosts.ini"


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_with_show_artifacts(mock_asyncio, mock_print, settings):
    mock_runner = MagicMock(status="successful", rc=0)
    mock_asyncio.to_thread = AsyncMock(return_value=mock_runner)

    svc = Ansible()
    await svc.run("connectors.yml", show_artifacts=["connector"])

    mock_print.assert_called_once_with(mock_runner, ["connector"])


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_user_group_in_extravars(mock_asyncio, mock_print, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock(status="successful", rc=0))

    svc = Ansible()
    await svc.run("connectors.yml")

    _, kwargs = mock_asyncio.to_thread.call_args
    assert kwargs["extravars"]["user_connector"] == "user"
    assert kwargs["extravars"]["group_connector"] == "group"


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_no_private_key(mock_asyncio, mock_print, settings):
    settings.ansible.ssh_private_key = ""
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock(status="successful", rc=0))

    svc = Ansible()
    await svc.run("connectors.yml")

    _, kwargs = mock_asyncio.to_thread.call_args
    assert "cmdline" not in kwargs


@patch("argo_automation_cpas.ansible.print_artifacts")
@patch("argo_automation_cpas.ansible.asyncio")
async def test_run_failed(mock_asyncio, mock_print, settings):
    mock_runner = MagicMock(status="failed", rc=2)
    mock_asyncio.to_thread = AsyncMock(return_value=mock_runner)

    svc = Ansible()
    result = await svc.run("connectors.yml")

    assert result is False
