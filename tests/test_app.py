import json

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

from argo_automation_cpas.app import Application


@pytest.fixture
def settings():
    return SimpleNamespace(
        request_timeout=30.0,
        verify_ssl=True,
        ansible_private_data_dir="/tmp/ansible",
        ansible_playbook="init.yml",
        general=SimpleNamespace(),
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
        ),
        statusapi=SimpleNamespace(
            api="https://api-status.devel.mon.argo.grnet.gr/v1/automation/tenants/{tenant_id}/status",
        ),
    )


# ---------------------------------------------------------------------------
# run: --clean-artifacts
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.clean_artifacts")
async def test_run_clean_artifacts(mock_clean, settings):
    app = Application(settings, clean_artifacts=[])
    await app.run()
    mock_clean.assert_called_once_with("/tmp/ansible/artifacts", [])


@patch("argo_automation_cpas.app.clean_artifacts")
async def test_run_clean_artifacts_with_roles(mock_clean, settings):
    app = Application(settings, clean_artifacts=["connector"])
    await app.run()
    mock_clean.assert_called_once_with("/tmp/ansible/artifacts", ["connector"])


# ---------------------------------------------------------------------------
# run: --only-ansible
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.ansible")
async def test_run_only_ansible(mock_ansible, settings):
    mock_ansible.run = AsyncMock()
    app = Application(settings, only_ansible="connectors.yml", inventory="hosts.ini",
                      add_tenants=["egi"], remove_tenants=["eudat"], show_artifacts=[])
    await app.run()
    mock_ansible.run.assert_called_once_with(
        settings, "connectors.yml",
        inventory="hosts.ini",
        add_tenants=["egi"],
        remove_tenants=["eudat"],
        show_artifacts=[],
    )


# ---------------------------------------------------------------------------
# run: --only-webapi
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.webapi")
async def test_run_only_webapi(mock_webapi, settings):
    mock_webapi.run = AsyncMock()
    app = Application(settings, only_webapi=True)
    await app.run()
    mock_webapi.run.assert_called_once_with(settings)


# ---------------------------------------------------------------------------
# run: --only-iam
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.client_session")
@patch("argo_automation_cpas.app.iam")
async def test_run_only_iam(mock_iam, mock_cs, settings, capsys):
    mock_iam.fetch_token = AsyncMock(return_value="iam-token-123")
    session = AsyncMock()
    mock_cs.return_value.__aenter__ = AsyncMock(return_value=session)
    mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

    app = Application(settings, only_iam=True)
    await app.run()

    mock_iam.fetch_token.assert_called_once_with(session, settings)
    assert "iam-token-123" in capsys.readouterr().out


@patch("argo_automation_cpas.app.client_session")
@patch("argo_automation_cpas.app.iam")
async def test_run_only_iam_no_token(mock_iam, mock_cs, settings, capsys):
    mock_iam.fetch_token = AsyncMock(return_value=None)
    session = AsyncMock()
    mock_cs.return_value.__aenter__ = AsyncMock(return_value=session)
    mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

    app = Application(settings, only_iam=True)
    await app.run()

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# run: --only-statusapi
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.client_session")
@patch("argo_automation_cpas.app.statusapi")
@patch("argo_automation_cpas.app.iam")
async def test_run_only_statusapi(mock_iam, mock_statusapi, mock_cs, settings):
    mock_iam.fetch_token = AsyncMock(return_value="iam-tok")
    mock_statusapi.fetch_status = AsyncMock()

    iam_session = AsyncMock()
    statusapi_session = AsyncMock()
    sessions = iter([
        MagicMock(__aenter__=AsyncMock(return_value=iam_session), __aexit__=AsyncMock(return_value=False)),
        MagicMock(__aenter__=AsyncMock(return_value=statusapi_session), __aexit__=AsyncMock(return_value=False)),
    ])
    mock_cs.side_effect = lambda *a, **kw: next(sessions)

    app = Application(settings, only_statusapi="tenant-abc")
    await app.run()

    mock_iam.fetch_token.assert_called_once_with(iam_session, settings)
    mock_statusapi.fetch_status.assert_called_once_with(statusapi_session, settings, "tenant-abc", "iam-tok")


# ---------------------------------------------------------------------------
# run: --only-ams
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.ams_mod")
@patch("argo_automation_cpas.app.asyncio")
async def test_run_only_ams(mock_asyncio, mock_ams_mod, settings):
    mock_ams_instance = MagicMock()
    mock_asyncio.to_thread = AsyncMock(return_value=mock_ams_instance)
    mock_ams_mod.pull_and_print = AsyncMock()

    app = Application(settings, only_ams=True)
    await app.run()

    mock_ams_mod.pull_and_print.assert_called_once_with(mock_ams_instance, settings)


# ---------------------------------------------------------------------------
# run: full flow
# ---------------------------------------------------------------------------

@patch("argo_automation_cpas.app.ansible")
@patch("argo_automation_cpas.app.webapi")
@patch("argo_automation_cpas.app.statusapi")
@patch("argo_automation_cpas.app.iam")
@patch("argo_automation_cpas.app.ams_mod")
@patch("argo_automation_cpas.app.client_session")
@patch("argo_automation_cpas.app.asyncio")
async def test_run_full_flow(
    mock_asyncio, mock_cs,
    mock_ams_mod, mock_iam, mock_statusapi, mock_webapi, mock_ansible,
    settings,
):
    mock_ams_instance = MagicMock()
    mock_asyncio.to_thread = AsyncMock(return_value=mock_ams_instance)

    mock_ams_mod.pull_message = AsyncMock(return_value={
        "tenant_name": "EGI", "tenant_id": "tid-1"
    })

    webapi_session = AsyncMock()
    iam_session = AsyncMock()
    statusapi_session = AsyncMock()
    sessions = iter([
        MagicMock(__aenter__=AsyncMock(return_value=webapi_session), __aexit__=AsyncMock(return_value=False)),
        MagicMock(__aenter__=AsyncMock(return_value=iam_session), __aexit__=AsyncMock(return_value=False)),
        MagicMock(__aenter__=AsyncMock(return_value=statusapi_session), __aexit__=AsyncMock(return_value=False)),
    ])
    mock_cs.side_effect = lambda *a, **kw: next(sessions)

    mock_iam.fetch_token = AsyncMock(return_value="iam-tok")
    mock_webapi.probe = AsyncMock()
    mock_webapi.fetch_topology_config = AsyncMock(return_value={"connector_tenant_topo_type": "GOCDB"})
    mock_statusapi.report_status = AsyncMock()
    mock_ansible.run = AsyncMock()

    app = Application(settings)
    await app.run()

    mock_ams_mod.pull_message.assert_called_once_with(mock_ams_instance, settings)
    mock_webapi.probe.assert_called_once_with(webapi_session, settings.webapi.url)
    mock_iam.fetch_token.assert_called_once_with(iam_session, settings)
    mock_statusapi.report_status.assert_called_once_with(
        statusapi_session, settings, "tid-1", "IN_PROGRESS", "iam-tok"
    )
    mock_webapi.fetch_topology_config.assert_called_once_with(
        webapi_session, settings.webapi.url_api_config
    )
    mock_ansible.run.assert_called_once()
    call_kwargs = mock_ansible.run.call_args
    assert call_kwargs.kwargs["webapi_overrides"] == {"connector_tenant_topo_type": "GOCDB"}


@patch("argo_automation_cpas.app.ams_mod")
@patch("argo_automation_cpas.app.asyncio")
async def test_run_full_flow_no_ams_message(mock_asyncio, mock_ams_mod, settings):
    mock_asyncio.to_thread = AsyncMock(return_value=MagicMock())
    mock_ams_mod.pull_message = AsyncMock(return_value=None)

    app = Application(settings)
    await app.run()

    mock_ams_mod.pull_message.assert_called_once()
