import sys
import unittest
import pytest
import asyncio

from argo_automation_cpas.monboxgit import *
from argo_automation_cpas.ams import *
from argo_automation_cpas.webapi import *
from argo_automation_cpas.restapi_tokens import *

_EMPTY_STRING = ""
_INVALID_TEST_TENANT_NAME = "TEST_ABCD1234_FFFFFFFF_INVALID"
_VALID_TEST_TENANT_NAME = "TEST_VALID_AUTOMATION_TENANT_YES"

_VALID_ARGO_TEST_TENANT_NAME = "AUTOMATION"


def test_add_tenant_to_yaml():
    monbox = MonboxGit()

    entry_info = _helper_create_dummy_tenant_entry_info()

    yaml_data = monbox._get_sensu_agent_config_yaml()
    yaml_data = monbox._add_new_tenant_to_agent_yaml(
        yaml_data, entry_info.tenant_agent_info
    )

    entry_key = entry_info.tenant_agent_info.tenant_name_lower
    assert entry_key in yaml_data[SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY]

    yaml_data = monbox._get_sensu_backend_config_yaml()
    yaml_data = monbox._add_new_tenant_to_backend_yaml(
        yaml_data, entry_info.tenant_backend_info
    )

    entry_key = entry_info.tenant_backend_info.tenant_name_lower
    assert entry_key in yaml_data[SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY]

    entry_key = monbox._get_tenant_pub_queue_entry_key(
        entry_info.tenant_backend_info.tenant_name
    )
    assert entry_key in yaml_data[SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY]


def test_remove_tenant_from_yaml():
    monbox = MonboxGit()

    # First: add new test tenant to yaml
    entry_info = _helper_create_dummy_tenant_entry_info()

    yaml_data = monbox._get_sensu_agent_config_yaml()
    yaml_data = monbox._add_new_tenant_to_agent_yaml(
        yaml_data, entry_info.tenant_agent_info
    )

    yaml_data = monbox._get_sensu_backend_config_yaml()
    yaml_data = monbox._add_new_tenant_to_backend_yaml(
        yaml_data, entry_info.tenant_backend_info
    )

    yaml_data = monbox._remove_tenant_from_agent_yaml(
        yaml_data, entry_info.tenant_agent_info.tenant_name_lower
    )

    entry_key = entry_info.tenant_agent_info.tenant_name_lower
    assert entry_key not in yaml_data[SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY]

    yaml_data = monbox._remove_tenant_from_backend_yaml(
        yaml_data, entry_info.tenant_backend_info.tenant_name_lower
    )

    entry_key = entry_info.tenant_backend_info.tenant_name_lower
    assert entry_key not in yaml_data[SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY]

    entry_key = monbox._get_tenant_pub_queue_entry_key(
        entry_info.tenant_backend_info.tenant_name
    )
    assert entry_key not in yaml_data[SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY]


def test_delete_invalid_tenant_1():
    monbox = MonboxGit()

    with pytest.raises(ValueError):
        monbox.remove_tenant(1234)


def test_delete_invalid_tenant_2():
    monbox = MonboxGit()

    with pytest.raises(ValueError):
        monbox.remove_tenant(_EMPTY_STRING)


def test_delete_invalid_tenant_3():
    monbox = MonboxGit()

    with pytest.raises(RuntimeError):
        monbox.remove_tenant(_INVALID_TEST_TENANT_NAME)


def test_delete_valid_tenant():
    monbox = MonboxGit()

    # make sure there is a valid test tenant available
    _helper_add_new_tenant(monbox, _VALID_TEST_TENANT_NAME)

    # delete said test tenant
    tenant_removed = monbox.remove_tenant(_VALID_TEST_TENANT_NAME)

    assert tenant_removed


@pytest.mark.asyncio
async def test_add_valid_tenant():
    monbox = MonboxGit()
    new_tenant_name = _VALID_ARGO_TEST_TENANT_NAME

    ams = await asyncio.to_thread(AMS().init)
    webapi = WebAPI()

    restapi_tokens_client = RestAPITokens()
    restapi_tokens = restapi_tokens_client.load_tokens()

    assert restapi_tokens is not None

    try:
        monbox.add_new_tenant(webapi, ams, new_tenant_name, restapi_tokens)

        success = monbox.commit_new_tenants()
        assert success

        monbox.clear_added_tenants()

        # IMPORTANT: Run w/o runner! We don't have a test machine to test out ansible runs.
        # Current start_monboxgit_runner() runs on prod machines; we don't want to test on prod machines.
        # That being said, the added tenant has correct tokens, so it is ready to be tested if we ever choose to do so.
        # await monboxgit.start_monboxgit_runner()

    finally:
        await ams.close()
        await webapi.close()


def _helper_create_dummy_tenant_entry_info() -> NewTenantEntryInfo:
    new_tenant_name = _VALID_TEST_TENANT_NAME
    tenant_name_lower = new_tenant_name.lower()
    restApiToken = "test-restapi-token"

    new_tenant_agent_info = NewTenantAgentInfo(
        tenant_name=new_tenant_name,
        tenant_poem_host=tenant_name_lower + ".poem.devel.mon.argo.grnet.gr",
        tenant_poem_token=restApiToken,
    )

    ams_token = "test-ams-token"
    webapi_token = "test-webapi-token"

    new_tenant_backend_info = NewTenantBackendInfo(
        tenant_name=new_tenant_name,
        ams_token=ams_token,
        webapi_token=webapi_token,
        poem_token=restApiToken,
    )

    return NewTenantEntryInfo(new_tenant_agent_info, new_tenant_backend_info)


def _helper_add_new_tenant(
    monbox: MonboxGit,
    new_tenant_name: str,
    restApiToken: str = "test-rest-api-token",
    ams_token: str = "test-ams-token",
    webapi_token: str = "test-webapi-token",
):
    tenant_name_lower = new_tenant_name.lower()
    new_tenant_agent_info = NewTenantAgentInfo(
        tenant_name=new_tenant_name,
        tenant_poem_host=tenant_name_lower + ".poem.devel.mon.argo.grnet.gr",
        tenant_poem_token=restApiToken,
    )

    new_tenant_backend_info = NewTenantBackendInfo(
        tenant_name=new_tenant_name,
        ams_token=ams_token,
        webapi_token=webapi_token,
        poem_token=restApiToken,
    )

    monbox._add_tenant_to_array(
        NewTenantEntryInfo(new_tenant_agent_info, new_tenant_backend_info)
    )

    monbox.commit_new_tenants()
