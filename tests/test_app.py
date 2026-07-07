import pytest
import asyncio

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import load_config

mocked_iam_token = 'IAM_TOKEN'
mocked_ams_events = [
    {
        "name": "INIT_MONGO",
        "properties": {
            "tenant_id": "184da7ca-5a64-4810-aa39-18cfaddbd44b",
            "tenant_name": "AUTOMATION"
        },
        "created_at": "2026-04-04T09:05:15.436443207Z"
    },
    {
        "name": "INIT_AMS",
        "properties": {
            "tenant_id": "184da7ca-5a64-4810-aa39-18cfaddbd44b",
            "tenant_name": "AUTOMATION"
        },
        "created_at": "2026-04-04T09:05:15.436443207Z"
    },
    {
        "name": "INIT_COMPUTE_ENGINE",
        "properties": {
            "tenant_id": "184da7ca-5a64-4810-aa39-18cfaddbd44b",
            "tenant_name": "AUTOMATION"
        },
        "created_at": "2026-04-04T09:05:15.436443207Z"
    },
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
                "name": "CHECK_READINESS",
                "status": "UNKNOWN",
                "start": None,
                "end": None,
                "message": None,
                "mode": "AUTO"
            },
            {
                "name": "CREATE_DOMAIN_NAMES",
                "status": "UNKNOWN",
                "start": None,
                "end": None,
                "message": "Waiting for manual administrator action",
                "mode": "MANUAL"
            },
            {
                "name": "INIT_TOPOLOGY_CONNECTOR",
                "status": "INITIALISED",
                "start": "2026-04-04T09:05:28Z",
                "end": None,
                "message": "Event notification: INIT_TOPOLOGY_CONNECTOR is initialised to Messaging Service for publishing",
                "mode": "AUTO",
                "properties": {
                    "tenant_id": "184da7ca-5a64-4810-aa39-18cfaddbd44b",
                    "tenant_name": "AUTOMATION"
                }
            },
            {
                "name": "INIT_MONITORING_BOX",
                "status": "UNKNOWN",
                "start": None,
                "end": None,
                "message": "Waiting for manual administrator action",
                "mode": "MANUAL"
            },
            {
                "name": "INIT_POEM",
                "status": "UNKNOWN",
                "start": None,
                "end": None,
                "message": "Waiting for manual administrator action",
                "mode": "MANUAL"
            }
        ]
    },
    "readiness": None
}


def cpas_test_settings(mocker):
    settings = load_config("tests/argo-cpas-tests.conf")
    mocker.patch('argo_automation_cpas.config._settings', new=settings)


def test_main_flow(mocker):
    cpas_test_settings(mocker)

    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = mocked_ams_events
    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = mocked_iam_token

    app = Application()
    asyncio.run(app.run())
