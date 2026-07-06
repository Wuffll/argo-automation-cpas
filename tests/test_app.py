import pytest
import asyncio

from argo_automation_cpas.app import Application

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


def test_main_flow(mocker):
    app = Application()

    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = mocked_ams_events
    asyncio.run(app.run())
