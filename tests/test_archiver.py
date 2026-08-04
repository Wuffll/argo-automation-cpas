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
def archiver_init_data():
    return SimpleNamespace(
        iam_token="IAM_TOKEN",
        tenant_id="184da7ca-5a64-4810-aa39-18cfaddbd44b",
        tenant_name="AUTOMATION",
        event="INIT_ARCHIVER",
        archiver_token="AUTOMATION-ARCHIVER",
        success_message=(
            "Archiver successfully configured for tenant AUTOMATION by "
            "argo-automation-cpas"
        ),
        status_url=(
            "https://API-STATUS_MON_ARGO/v1/automation/tenants/"
            "184da7ca-5a64-4810-aa39-18cfaddbd44b/status"
        ),
        ams_events=[
            {
                "name": "INIT_ARCHIVER",
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
                        "name": "INIT_ARCHIVER",
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
        expected_archiver_tenants=[
            {
                'tenant_name': 'automation',
                'ams_project': 'AUTOMATION',
                'archiver_token': 'AUTOMATION-ARGOARCHIVER',
                'ams_host': 'host-API_DEVEL_MSG_ARGO'
            }
        ],
        status_api_mock={
            "headers": {
                "Authorization": "Bearer IAM_TOKEN",
                "Accept": "application/json",
            }
        },
    )


def test_archiver_init(mocker, archiver_init_data, ansible_runner_ok):
    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = archiver_init_data.ams_events

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = archiver_init_data.iam_token

    statusapi_httpget = mocker.patch(
        'argo_automation_cpas.statusapi.SessionWithRetry.http_get'
    )
    statusapi_httpget.return_value = archiver_init_data.statusapi_jobs

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')

    ansible_runner_run = mocker.patch('argo_automation_cpas.ansible.ansible_runner.run')
    ansible_runner_run.return_value = ansible_runner_ok

    app = Application()
    asyncio.run(app.run())

    assert statusapi_httpget.call_args_list[0] == mocker.call(
        archiver_init_data.status_url,
        **archiver_init_data.status_api_mock
    )

    assert statusapi_updatejobstatus.call_args_list[0] == mocker.call(
        archiver_init_data.tenant_id,
        archiver_init_data.event,
        'IN_PROGRESS',
        archiver_init_data.iam_token,
    )

    assert 'extravars' in ansible_runner_run.call_args_list[0][1]
    assert 'archiver_tenants' in ansible_runner_run.\
        call_args_list[0][1]['extravars']
    assert ansible_runner_run.\
        call_args_list[0][1]['extravars']['archiver_tenants'] == archiver_init_data.expected_archiver_tenants

    assert statusapi_updatejobstatus.call_args_list[1] == mocker.call(
        archiver_init_data.tenant_id,
        archiver_init_data.event,
        'COMPLETED',
        archiver_init_data.iam_token,
        message=archiver_init_data.success_message
    )

    assert statusapi_updatejobstatus.call_count == 2
