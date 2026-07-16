import asyncio
from types import SimpleNamespace

import pytest

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import load_config


@pytest.fixture(autouse=True)
def cpas_test_settings(mocker):
    settings = load_config("tests/argo-cpas-tests.conf")
    mocker.patch('argo_automation_cpas.config._settings', new=settings)
    return settings


@pytest.fixture
def ansible_runner_ok():
    return SimpleNamespace(status="successful", rc=0)


@pytest.fixture
def poem_init_data():
    return SimpleNamespace(
        iam_token="IAM_TOKEN",
        tenant_id="184da7ca-5a64-4810-aa39-18cfaddbd44b",
        tenant_name="AUTOMATION",
        event="INIT_POEM",
        poemadmin_token="AUTOMATION-POEMADMIN",
        poemviewer_token="AUTOMATION-POEMVIEWER",
        success_message=(
            "POEM successfully configured for tenant AUTOMATION by "
            "argo-automation-cpas"
        ),
        status_url=(
            "https://API-STATUS_MON_ARGO/v1/automation/tenants/"
            "184da7ca-5a64-4810-aa39-18cfaddbd44b/status"
        ),
        ams_events=[
            {
                "name": "INIT_POEM",
                "properties": {
                    "tenant_id": "184da7ca-5a64-4810-aa39-18cfaddbd44b",
                    "tenant_name": "AUTOMATION",
                },
                "created_at": "2026-04-04T09:05:28.607501253Z",
            }
        ],
        statusapi_jobs={
            "name": "AUTOMATION",
            "status": {
                "jobs": [
                    {
                        "name": "INIT_POEM",
                        "status": "INITIALISED",
                        "start": None,
                        "end": None,
                        "message": "Waiting for manual administrator action",
                        "mode": "MANUAL",
                    }
                ]
            },
            "readiness": None,
        },
        expected_poem_tenants=[
            {
                'tenant_fqdn': 'automation.POEM-DEVEL-MON-ARGO',
                'tenant_name': 'AUTOMATION',
                'tenant_schema_name': 'automation',
                'tenant_namespace': 'CH.CERN.SAM',
                'tenant_privacypolicies': 'https://argo.egi.eu/egi/Critical/policies/',
                'tenant_samlloginstring': 'Login using EGI CHECK-IN',
                'tenant_samlservicename': 'ARGO POEM EGI-CheckIN',
                'tenant_superuser_email': 'argo-ggus-support@grnet.gr',
                'tenant_superuser_name': 'poem',
                'tenant_superuser_password': 'POEM_SUPERUSER_SECRET',
                'tenant_termsofuse': 'https://argo.egi.eu/egi/Critical/termsofUse',
                'tokens': {
                    'restapi': 'AUTOMATION-RESTAPI',
                    'webapi_ro': 'AUTOMATION-POEMVIEWER',
                    'webapi_rw': 'AUTOMATION-POEMADMIN'
                }
            }
        ],
        status_api_mock={
            "headers": {
                "Authorization": "Bearer IAM_TOKEN",
                "Accept": "application/json",
            }
        },
    )


def test_poem_init(mocker, poem_init_data, ansible_runner_ok):
    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = poem_init_data.ams_events

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = poem_init_data.iam_token

    statusapi_httpget = mocker.patch('argo_automation_cpas.statusapi.SessionWithRetry.http_get')
    statusapi_httpget.return_value = poem_init_data.statusapi_jobs

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')

    ansible_runner_run = mocker.patch('argo_automation_cpas.ansible.ansible_runner.run')
    ansible_runner_run.return_value = ansible_runner_ok

    app = Application()
    asyncio.run(app.run())

    assert statusapi_httpget.call_args_list[0] == mocker.call(
        poem_init_data.status_url,
        **poem_init_data.status_api_mock
    )

    assert statusapi_updatejobstatus.call_args_list[0] == mocker.call(
        poem_init_data.tenant_id,
        poem_init_data.event,
        'IN_PROGRESS',
        poem_init_data.iam_token,
    )

    assert 'extravars' in ansible_runner_run.call_args_list[0][1]
    assert 'poem_tenants' in ansible_runner_run.\
        call_args_list[0][1]['extravars']
    assert ansible_runner_run.\
        call_args_list[0][1]['extravars']['poem_tenants'] == poem_init_data.expected_poem_tenants

    assert statusapi_updatejobstatus.call_args_list[1] == mocker.call(
        poem_init_data.tenant_id,
        poem_init_data.event,
        'COMPLETED',
        poem_init_data.iam_token,
        message=poem_init_data.success_message
    )

    assert statusapi_updatejobstatus.call_count == 2


@pytest.fixture
def poem_init_data_2():
    return SimpleNamespace(
        iam_token="IAM_TOKEN",
        tenant_id="11111111-5a64-4810-aa39-18cfaddbd44b",
        tenant_name="INSTRUCT-ERIC",
        event="INIT_POEM",
        poemadmin_token="INSTRUCT-ERIC-POEMADMIN",
        poemviewer_token="INSTRUCT-ERIC-POEMVIEWER",
        success_message=(
            "POEM successfully configured for tenant INSTRUCT-ERIC by "
            "argo-automation-cpas"
        ),
        status_url=(
            "https://API-STATUS_MON_ARGO/v1/automation/tenants/"
            "11111111-5a64-4810-aa39-18cfaddbd44b/status"
        ),
        ams_events=[
            {
                "name": "INIT_POEM",
                "properties": {
                    "tenant_id": "11111111-5a64-4810-aa39-18cfaddbd44b",
                    "tenant_name": "INSTRUCT-ERIC",
                },
                "created_at": "2026-04-04T09:05:28.607501253Z",
            }
        ],
        statusapi_jobs={
            "name": "INSTRUCT-ERIC",
            "status": {
                "jobs": [
                    {
                        "name": "INIT_POEM",
                        "status": "INITIALISED",
                        "start": None,
                        "end": None,
                        "message": "Waiting for manual administrator action",
                        "mode": "MANUAL",
                    }
                ]
            },
            "readiness": None,
        },
        expected_poem_tenants=[
            {
                'tenant_fqdn': 'instruct-eric.POEM-DEVEL-MON-ARGO',
                'tenant_name': 'INSTRUCT-ERIC',
                'tenant_schema_name': 'instructeric',
                'tenant_namespace': 'CH.CERN.SAM',
                'tenant_privacypolicies': 'https://argo.egi.eu/egi/Critical/policies/',
                'tenant_samlloginstring': 'Login using EGI CHECK-IN',
                'tenant_samlservicename': 'ARGO POEM EGI-CheckIN',
                'tenant_superuser_email': 'argo-ggus-support@grnet.gr',
                'tenant_superuser_name': 'poem',
                'tenant_superuser_password': 'POEM_SUPERUSER_SECRET',
                'tenant_termsofuse': 'https://argo.egi.eu/egi/Critical/termsofUse',
                'tokens': {
                    'restapi': 'INSTRUCT-ERIC-RESTAPI',
                    'webapi_ro': 'INSTRUCT-ERIC-POEMVIEWER',
                    'webapi_rw': 'INSTRUCT-ERIC-POEMADMIN'
                }
            }
        ],
        status_api_mock={
            "headers": {
                "Authorization": "Bearer IAM_TOKEN",
                "Accept": "application/json",
            }
        },
    )


def test_poem_init_2(mocker, ansiblerun, poem_init_data_2, ansible_runner_ok):
    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = poem_init_data_2.ams_events

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = poem_init_data_2.iam_token

    statusapi_httpget = mocker.patch('argo_automation_cpas.statusapi.SessionWithRetry.http_get')
    statusapi_httpget.return_value = poem_init_data_2.statusapi_jobs

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')

    if ansiblerun:
        ansible_runner_run = None
        app = Application(show_artifacts=True)
    else:
        ansible_runner_run = mocker.patch('argo_automation_cpas.ansible.ansible_runner.run')
        ansible_runner_run.return_value = ansible_runner_ok
        app = Application()

    asyncio.run(app.run())

    assert statusapi_httpget.call_args_list[0] == mocker.call(
        poem_init_data_2.status_url,
        **poem_init_data_2.status_api_mock
    )

    assert statusapi_updatejobstatus.call_args_list[0] == mocker.call(
        poem_init_data_2.tenant_id,
        poem_init_data_2.event,
        'IN_PROGRESS',
        poem_init_data_2.iam_token,
    )

    if not ansiblerun:
        assert 'extravars' in ansible_runner_run.call_args_list[0][1]
        assert 'poem_tenants' in ansible_runner_run.\
            call_args_list[0][1]['extravars']
        assert ansible_runner_run.\
            call_args_list[0][1]['extravars']['poem_tenants'] == poem_init_data_2.expected_poem_tenants

    assert statusapi_updatejobstatus.call_args_list[1] == mocker.call(
        poem_init_data_2.tenant_id,
        poem_init_data_2.event,
        'COMPLETED',
        poem_init_data_2.iam_token,
        message=poem_init_data_2.success_message
    )

    assert statusapi_updatejobstatus.call_count == 2
