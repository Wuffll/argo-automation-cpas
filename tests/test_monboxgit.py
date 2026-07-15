import pytest

from argo_automation_cpas.monboxgit import (MonboxGit, NewTenantEntryInfo,
                                            NewTenantAgentInfo, NewTenantBackendInfo,
                                            SENSU_AGENT_TENANT_DATA_YAML_ENTRY_KEY, SENSU_BACKEND_PUB_QUEUE_YAML_ENTRY_KEY,
                                            SENSU_BACKEND_TENANT_SECTION_YAML_ENTRY_KEY)
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.config import load_config

__TEST_AGENT_CONFIG_YAML = """
argo::mon::caupdate::script_source: puppet:///modules/argo/mon/caupdate/update_ca_bundle_sensu
argo::mon::poemtools::tenants_data:
  test-topology:
    poem_host: test-topology.poem.devel.mon.argo.grnet.gr
    poem_token: test-rest-api-token
    profiles: ARGO_MON, ARGO_MON_INTERNAL
  srce:
    poem_host: srce.poem.devel.mon.argo.grnet.gr
    poem_token: test-rest-api-token
    profiles: default_metric
  test_valid_automation_tenant_yes:
    poem_host: test_valid_automation_tenant_yes.poem.devel.mon.argo.grnet.gr
    poem_token: test-rest-api-token
    profiles: default_metric
"""

__TEST_BACKEND_CONFIG_YAML = """
argo::mon::amspublisher::runuser: sensu
argo::mon::amspublisher::publisher_queues_topics:
  MetricsTEST-TOPOLOGY: null
  MetricsTESTTOPOLOGY:
    Directory: /var/spool/ams-publisher/test-topology_metrics/
    Rate: '1'
    Host: api.devel.msg.argo.grnet.gr
    Key: test-ams-key
    Project: TEST-TOPOLOGY
    Topic: metric_data
    Bulksize: '1'
    MsgType: metric_data
    Avro: 'True'
    AvroSchema: /etc/ams-publisher/metric_data.avsc
    Retry: '300'
    Timeout: '60'
    SleepRetry: '300'
  Metricssrce:
    Directory: /var/spool/ams-publisher/srce_metrics/
    Rate: '1'
    Host: api.devel.msg.argo.grnet.gr
    Key: test_ams_key
    Project: SRCE
    Topic: metric_data
    Bulksize: '1'
    MsgType: metric_data
    Avro: 'True'
    AvroSchema: /etc/ams-publisher/metric_data.avsc
    Retry: '300'
    Timeout: '60'
    SleepRetry: '300'
  Metricstest_valid_automation_tenant_yes:
    Directory: /var/spool/ams-publisher/test_valid_automation_tenant_yes_metrics/
    Rate: '1'
    Host: api.devel.msg.argo.grnet.gr
    Key: test-ams-token
    Project: TEST_VALID_AUTOMATION_TENANT_YES
    Topic: metric_data
    Bulksize: '1'
    MsgType: metric_data
    Avro: 'True'
    AvroSchema: /etc/ams-publisher/metric_data.avsc
    Retry: '300'
    Timeout: '60'
    SleepRetry: '300'
argo::mon::poemtools::tenants_data:
  default:
    poem_host: internal.poem.devel.mon.argo.grnet.gr
    poem_token: test-poem-token
    profiles: ARGO_MON_SELF
argo::mon::scg::topology: puppet:///private/scg/topology
argo::mon::scg::sensu_url: https://sensu-backend-auto.devel.mon.argo.grnet.gr:8080
argo::mon::scg::sensu_token: sensu_token
argo::mon::scg::webapi_url: https://api.devel.mon.argo.grnet.gr
argo::mon::scg::tenant_sections:
  default:
    poem_url: https://internal.poem.devel.mon.argo.grnet.gr
    poem_token: test-poem-token
    webapi_token: test-webapi-token
    metricprofiles: ARGO_MON_SELF
    topology: /etc/argo-scg/topology.d/self_topology.json
    secrets: /etc/sensu/secret_envs
    publish: 'false'
  test-topology:
    poem_url: https://test-topology.poem.devel.mon.argo.grnet.gr/
    poem_token: test-poem-token
    webapi_token: test-webapi-token
    metricprofiles: ARGO_MON, ARGO_MON_INTERNAL
    publish: 'true'
    secrets: /etc/sensu/secret_envs
    publisher_queue: /var/spool/ams-publisher/test-topology_metrics/
    namespace: auto
  srce:
    poem_url: https://srce.poem.devel.mon.argo.grnet.gr
    poem_token: test-poem-token
    webapi_token: test-webapi-token
    metricprofiles: default_metric
    publish: 'true'
    secrets: /etc/sensu/secret_envs
    publisher_queue: /var/spool/ams-publisher/srce_metrics/
    namespace: auto
  test_valid_automation_tenant_yes:
    poem_url: https://test_valid_automation_tenant_yes.poem.devel.mon.argo.grnet.gr
    poem_token: test-rest-api-token
    webapi_token: test-webapi-token
    metricprofiles: default_metric
    publish: 'true'
    secrets: /etc/sensu/secret_envs
    publisher_queue: /var/spool/ams-publisher/test_valid_automation_tenant_yes_metrics/
    namespace: auto
"""

_EMPTY_STRING = ""
_INVALID_TEST_TENANT_NAME = "TEST_ABCD1234_FFFFFFFF_INVALID"
_VALID_TEST_TENANT_NAME = "TEST_VALID_AUTOMATION_TENANT_YES"
_VALID_ARGO_TEST_TENANT_NAME = "AUTOMATION"


@pytest.fixture(autouse=True)
def cpas_test_settings(mocker):
    settings = load_config("tests/argo-cpas-tests.conf")
    mocker.patch("argo_automation_cpas.config._settings", new=settings)
    return settings


def test_add_tenant_to_yaml(mocker):
    mocker.patch.object(
        MonboxGit,
        "_get_sensu_agent_config",
        return_value=__TEST_AGENT_CONFIG_YAML,
    )
    mocker.patch.object(
        MonboxGit,
        "_get_sensu_backend_config",
        return_value=__TEST_BACKEND_CONFIG_YAML,
    )

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


def test_remove_tenant_from_yaml(mocker):
    mocker.patch.object(
        MonboxGit,
        "_get_sensu_agent_config",
        return_value=__TEST_AGENT_CONFIG_YAML,
    )
    mocker.patch.object(
        MonboxGit,
        "_get_sensu_backend_config",
        return_value=__TEST_BACKEND_CONFIG_YAML,
    )

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


def test_delete_invalid_tenant_number_input():
    monbox = MonboxGit()

    with pytest.raises(ValueError):
        monbox.remove_tenant(1234)


def test_delete_invalid_tenant_empty_string_input():
    monbox = MonboxGit()

    with pytest.raises(ValueError):
        monbox.remove_tenant(_EMPTY_STRING)


def test_delete_invalid_tenant_nonexistant_tenant(mocker):
    monbox = MonboxGit()

    backend_mock_func = mocker.Mock()
    backend_mock_func.return_value = __TEST_BACKEND_CONFIG_YAML

    agent_mock_func = mocker.Mock()
    agent_mock_func.return_value = __TEST_AGENT_CONFIG_YAML

    mocker.patch.object(MonboxGit, "_get_sensu_backend_config", backend_mock_func)
    mocker.patch.object(MonboxGit, "_get_sensu_agent_config", agent_mock_func)

    with pytest.raises(RuntimeError):
        monbox.remove_tenant(_INVALID_TEST_TENANT_NAME)


def test_delete_valid_tenant(mocker):
    config = get_settings()

    # setup mock function
    commit_mock_func = mocker.Mock()
    commit_mock_func.return_value = True

    backend_mock_func = mocker.Mock()
    backend_mock_func.return_value = __TEST_BACKEND_CONFIG_YAML

    agent_mock_func = mocker.Mock()
    agent_mock_func.return_value = __TEST_AGENT_CONFIG_YAML

    mocker.patch.object(MonboxGit, "_commit_file_to_git_repo", commit_mock_func)
    mocker.patch.object(MonboxGit, "_get_sensu_backend_config", backend_mock_func)
    mocker.patch.object(MonboxGit, "_get_sensu_agent_config", agent_mock_func)

    monbox = MonboxGit()

    tenant_to_delete = _VALID_TEST_TENANT_NAME

    # Delete said test tenant
    monbox.remove_tenant(tenant_to_delete)

    assert (
        len(commit_mock_func.mock_calls) == 2
    ), "_commit_file_to_git_repo should be called two times! Once for backend config, once for agent config."

    assert (
        len(backend_mock_func.mock_calls) == 1
    ), "Get backend yaml function must be called to remove tenant"

    assert (
        len(agent_mock_func.mock_calls) == 1
    ), "Get agent yaml function must be called to remove tenant"

    # ordering in the following two arrays matter!
    branch_array: list[str] = [
        config.monboxgit.git_branch_backend,
        config.monboxgit.git_branch_agent,
    ]
    directory_array: list[str] = [
        config.monboxgit.backend_config_file_path,
        config.monboxgit.agent_config_file_path,
    ]

    for call in commit_mock_func.mock_calls:
        commit_index = -1

        kwargs = call.kwargs

        assert (
            f"{tenant_to_delete.lower()}" not in kwargs["content"]
        ), f"{tenant_to_delete.lower()} (tenant_to_delete.lower()) found!"

        owner = kwargs.get("owner", -1)
        assert owner != -1, "Owner value not set for git push"
        assert (
            owner == config.monboxgit.git_repo_owner
        ), "Repo owner variable value not the same as config file"

        repo = kwargs.get("repo", -1)
        assert repo != -1, "Repo value not set for git push"
        assert (
            repo == config.monboxgit.git_repo_name
        ), "Repo name variable value not the same as config file"

        # make sure the directory kwarg is set properly
        found_branch = kwargs.get("branch", -1)
        assert found_branch != -1, "Branch not set kwargs for git push"

        found_branch_index = branch_array.index(found_branch)
        assert found_branch_index != -1, (
            f"Unable to find branch {found_branch} in branch array"
            "(happens if you push to the same branch twice or to an invalid branch)"
        )

        commit_index = found_branch_index

        # make sure git branch and file path for that branch match
        assert (
            kwargs.get("directory", "") == directory_array[commit_index]
        ), f"Unable to find directory file for branch {found_branch}"

        del branch_array[commit_index]
        del directory_array[commit_index]


@pytest.mark.asyncio
async def test_add_valid_tenant(mocker):
    config = get_settings()

    new_tenant_name = _VALID_ARGO_TEST_TENANT_NAME

    ams = mocker.Mock()
    ams.tokens.load_tokens.return_value = {
        new_tenant_name: {
            "argo-monbox": "AUTOMATION-ARGOMONBOX",
        }
    }
    webapi = mocker.Mock()
    webapi.tokens.load_tokens.return_value = {
        new_tenant_name: {
            "monbox": "AUTOMATION-MONBOX",
        }
    }
    restapi_tokens = {
        new_tenant_name: {
            "restapi": "AUTOMATION-RESTAPI",
        }
    }

    mock_func = mocker.Mock()
    mock_func.return_value = True

    mocker.patch.object(MonboxGit, "_commit_file_to_git_repo", mock_func)
    mocker.patch.object(
        MonboxGit,
        "_get_sensu_agent_config",
        return_value=__TEST_AGENT_CONFIG_YAML,
    )
    mocker.patch.object(
        MonboxGit,
        "_get_sensu_backend_config",
        return_value=__TEST_BACKEND_CONFIG_YAML,
    )

    monbox = MonboxGit()

    monbox.add_new_tenant(webapi, ams, new_tenant_name, restapi_tokens)
    monbox.commit_new_tenants()
    monbox.clear_added_tenants()

    # IMPORTANT: Run w/o runner! We don't have a test machine to test out ansible runs.
    # Current start_monboxgit_runner() runs on prod machines; we don't want to test on prod machines.
    # That being said, the added tenant has correct tokens, so it is ready to be tested if we ever choose to do so.
    # await monboxgit.start_monboxgit_runner()

    assert (
        len(mock_func.mock_calls) == 2
    ), "_commit_file_to_git_repo should be called twice! Once for backend config, one for agent."

    # ordering in the following two arrays matter!
    branch_array: list[str] = [
        config.monboxgit.git_branch_backend,
        config.monboxgit.git_branch_agent,
    ]
    directory_array: list[str] = [
        config.monboxgit.backend_config_file_path,
        config.monboxgit.agent_config_file_path,
    ]

    for call in mock_func.mock_calls:
        commit_index = -1

        kwargs = call.kwargs

        assert (
            f"{new_tenant_name.lower()}" in kwargs["content"]
        ), f"{new_tenant_name.lower()} (new_tenant_name.lower()) not found!"

        owner = kwargs.get("owner", -1)
        assert owner != -1, "Owner value not set for git push"
        assert (
            owner == config.monboxgit.git_repo_owner
        ), "Repo owner variable value not the same as config file"

        repo = kwargs.get("repo", -1)
        assert repo != -1, "Repo value not set for git push"
        assert (
            repo == config.monboxgit.git_repo_name
        ), "Repo name variable value not the same as config file"

        # make sure the directory kwarg is set properly
        found_branch = kwargs.get("branch", -1)
        assert found_branch != -1, "Branch not set kwargs for git push"

        found_branch_index = branch_array.index(found_branch)
        assert found_branch_index != -1, (
            f"Unable to find branch {found_branch} in branch array"
            "(happens if you push to the same branch twice or to an invalid branch)"
        )

        commit_index = found_branch_index

        # make sure git branch and file path for that branch match
        assert (
            kwargs.get("directory", "") == directory_array[commit_index]
        ), f"Unable to find directory file for branch {found_branch}"

        del branch_array[commit_index]
        del directory_array[commit_index]


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
