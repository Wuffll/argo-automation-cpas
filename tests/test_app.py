import pytest
import asyncio

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import load_config

mocked_iam_token = 'IAM_TOKEN'
mocked_ams_events = [
    {
        "name": "INIT_TOPOLOGY_CONNECTOR",
        "properties": {
            "tenant_id": "184da7ca-5a64-4810-aa39-18cfaddbd44b",
            "tenant_name": "AUTOMATION"
        },
        "created_at": "2026-04-04T09:05:28.607501253Z"
    }
]

mocked_statusapi_jobs = {
    "name": "AUTOMATION",
    "status":
    {
        "jobs": [
            {
                "name": "INIT_TOPOLOGY_CONNECTOR",
                "status": "INITIALISED",
                "start": None,
                "end": None,
                "message": "Waiting for manual administrator action",
                "mode": "MANUAL"
            }
        ]
    },
    "readiness": None
}

mocked_webapi_topoconfig = {
    "type": "CSV",
    "feed_url": """https://docs.google.com/spreadsheets/d/
                 1xiptZgYG2bn78hwBCEP7esTDyfMvvEXFLfJY2HblfI8/
                 export?gid=0&format=csv""",
    "paginated": "false",
    "fetch_type": [
        "ServiceGroups"
    ],
    "uid_endpoints": ""
}


def cpas_test_settings(mocker):
    settings = load_config("tests/argo-cpas-tests.conf")
    mocker.patch('argo_automation_cpas.config._settings', new=settings)


def test_connector_init(mocker):
    cpas_test_settings(mocker)

    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = mocked_ams_events
    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = mocked_iam_token

    statusapi_httpget = mocker.patch('argo_automation_cpas.statusapi.SessionWithRetry.http_get')
    statusapi_httpget.return_value = mocked_statusapi_jobs

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')
    webapi_fetchtopologyconfig = mocker.patch('argo_automation_cpas.webapi.WebAPI.fetch_topology_config')
    webapi_fetchtopologyconfig.return_value = mocked_webapi_topoconfig

    ansible_runner = mocker.patch('argo_automation_cpas.ansible.ansible_runner')

    app = Application()
    asyncio.run(app.run())

    statusapi_httpget.assert_called_with(
        'FOO'
    )

    statusapi_updatejobstatus.assert_called_with(
        'FOO'
    )

    webapi_fetchtopologyconfig.assert_called_with(
        'FOO'
    )
