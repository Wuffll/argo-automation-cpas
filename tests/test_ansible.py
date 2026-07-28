import pytest
from unittest.mock import patch
from unittest.mock import MagicMock
import unittest
from types import SimpleNamespace


from argo_automation_cpas.ansible import *
import argo_automation_cpas.ansible


@pytest.mark.asyncio
async def test_ansible_run():
    with patch("argo_automation_cpas.ansible.ansible_runner.run") as mock_runner:
        mock_runner.return_value = {"status": "Mocked", "rc": 999}

        mock_runner.return_value = "MockRun"

        ansible = Ansible()
        output = await ansible.run("")

        print("Output = " + str(output))

        # Here you can test out whether ansible has everything set properly before the run
        # print(str(mock_runner.call_args.kwargs))

        mock_runner.assert_called_once()


def test_connector_extravars_include_tenant_webapi_token_from_manual_tokens():
    ansible = Ansible()
    ansible.settings.ansible.tokens = {
        "default": {
            "webapi": "WEBAPI_TOKEN",
        },
    }

    extravars = ansible._connector_extravars(None, None, ["AUTOMATION"], None)

    assert extravars["connector_tenants"][0]["tenant_webapi_token"] == "WEBAPI_TOKEN"


@pytest.mark.asyncio
async def test_connector_run_with_some_missing_tenant_webapi_tokens_skips_only_missing_tenants():
    to_thread_calls = []

    async def fake_to_thread(func, **kwargs):
        to_thread_calls.append((func, kwargs))
        return SimpleNamespace(status="successful", rc=0)

    with patch("argo_automation_cpas.ansible.asyncio.to_thread", new=fake_to_thread):
        ansible = Ansible()
        ansible.settings.ansible.tokens = {}

        ok, kwargs = await ansible.run(
            "connectors.yml",
            component_tokens={"READY": {"tenant-connector": "READY_TOKEN"}},
            add_tenants=["AUTOMATION", "READY"],
        )

        assert ok is True
        assert kwargs["extravars"]["connector_tenants"] == [
            {
                **ansible.connector_tenant_defaults,
                "tenant_name": "READY",
                "tenant_webapi_token": "READY_TOKEN",
            }
        ]
        assert len(to_thread_calls) == 1
        assert to_thread_calls[0][1]["extravars"]["connector_tenants"] == (
            kwargs["extravars"]["connector_tenants"]
        )


@pytest.mark.asyncio
async def test_connector_run_without_any_tenant_webapi_token_skips_ansible_runner():
    with patch("argo_automation_cpas.ansible.ansible_runner.run") as mock_runner:
        ansible = Ansible()
        ansible.settings.ansible.tokens = {}

        ok, kwargs = await ansible.run(
            "connectors.yml",
            component_tokens={},
            add_tenants=["AUTOMATION"],
        )

        assert ok is False
        assert kwargs["extravars"]["connector_tenants"] == []
        mock_runner.assert_not_called()
