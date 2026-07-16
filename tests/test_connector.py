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
def connector_init_csv_data():
    return SimpleNamespace(
        iam_token="IAM_TOKEN",
        tenant_id="184da7ca-5a64-4810-aa39-18cfaddbd44b",
        tenant_name="AUTOMATION",
        event="INIT_TOPOLOGY_CONNECTOR",
        connector_token="AUTOMATION-CONNECTOR",
        success_message=(
            "Connector successfully configured for tenant AUTOMATION by "
            "argo-automation-cpas"
        ),
        topology_feed_url=(
            "https://docs.google.com/spreadsheets/d/"
            "1xiptZgYG2bn78hwBCEP7esTDyfMvvEXFLfJY2HblfI8/export?gid=0&format=csv"
        ),
        topology_config_url="/api/v2/feeds/topology",
        status_url=(
            "https://API-STATUS_MON_ARGO/v1/automation/tenants/"
            "184da7ca-5a64-4810-aa39-18cfaddbd44b/status"
        ),
        ams_events=[
            {
                "name": "INIT_TOPOLOGY_CONNECTOR",
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
                        "name": "INIT_TOPOLOGY_CONNECTOR",
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
        webapi_topoconfig={
            "connector_tenant_topo_type": "CSV",
            "connector_tenant_topo_feed": (
                "https://docs.google.com/spreadsheets/d/"
                "1xiptZgYG2bn78hwBCEP7esTDyfMvvEXFLfJY2HblfI8/export?gid=0&format=csv"
            ),
            "paginated": "false",
            "fetch_type": [
                "ServiceGroups",
            ],
            "uid_endpoints": "",
        },
        expected_connector_tenants=[
            {
                "tenant_name": "AUTOMATION",
                "tenant_topo_type": "CSV",
                "tenant_cron_weights_disable": True,
                "tenant_cron_downtimes_disable": True,
                "tenant_webapi_token": "AUTOMATION-CONNECTOR",
                "tenant_bdii": False,
                "tenant_jobs": [
                    {
                        "name": "CORE",
                        "dirname": "CORE",
                    }
                ],
                "tenant_auth_useplainhttpauth": False,
                "tenant_topo_fetchtype": "ServiceGroups",
                "tenant_topo_uidserviceendpoints": True,
                "tenant_topo_feed": (
                    "https://docs.google.com/spreadsheets/d/"
                    "1xiptZgYG2bn78hwBCEP7esTDyfMvvEXFLfJY2HblfI8/export?gid=0&format=csv"
                ),
            }
        ],
        status_api_mock={
            "headers": {
                "Authorization": "Bearer IAM_TOKEN",
                "Accept": "application/json",
            }
        },
    )


@pytest.fixture
def connector_init_eosc_service_data():
    return SimpleNamespace(
        iam_token="IAM_TOKEN",
        tenant_id="184da7ca-5a64-4810-aa39-18cfaddbd44b",
        tenant_name="AUTOMATION",
        event="INIT_TOPOLOGY_CONNECTOR",
        connector_token="AUTOMATION-CONNECTOR",
        success_message=(
            "Connector successfully configured for tenant AUTOMATION by "
            "argo-automation-cpas"
        ),
        topology_feed_url=(
            "https://docs.google.com/spreadsheets/d/"
            "1xiptZgYG2bn78hwBCEP7esTDyfMvvEXFLfJY2HblfI8/export?gid=0&format=csv"
        ),
        topology_config_url="/api/v2/feeds/topology",
        status_url=(
            "https://API-STATUS_MON_ARGO/v1/automation/tenants/"
            "184da7ca-5a64-4810-aa39-18cfaddbd44b/status"
        ),
        ams_events=[
            {
                "name": "INIT_TOPOLOGY_CONNECTOR",
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
                        "name": "INIT_TOPOLOGY_CONNECTOR",
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
        webapi_topoconfig={
            "status": {
                "message": "Success",
                "code": "200"
            },
            "data": [
                {
                    "type": "eosc-service-catalog",
                    "feed_service_groups": "https://cat.ni4os.eu/api/provider/all",
                    "feed_service_endpoints": "https://cat.ni4os.eu/api/service/all",
                    "feed_service_endpoints_extensions": "https://cat.ni4os.eu/api/configurationTemplateInstance/all"
                }
            ]
        },
        expected_connector_tenants=[
            {
                'tenant_auth_useplainhttpauth': False,
                'tenant_bdii': False,
                'tenant_cron_downtimes_disable': True,
                'tenant_cron_weights_disable': True,
                'tenant_jobs': [{'dirname': 'CORE', 'name': 'CORE'}],
                'tenant_name': 'AUTOMATION',
                'tenant_topo_feed': 'http://dummy.csv',
                'tenant_topo_feedserviceendpoints': 'https://cat.ni4os.eu/api/service/all',
                'tenant_topo_feedserviceendpointsext': 'https://cat.ni4os.eu/api/configurationTemplateInstance/all',
                'tenant_topo_feedservicegroups': 'https://cat.ni4os.eu/api/provider/all',
                'tenant_topo_fetchtype': 'ServiceGroups',
                'tenant_topo_type': 'PROVIDER',
                'tenant_topo_uidserviceendpoints': True,
                'tenant_webapi_token': 'AUTOMATION-CONNECTOR'
            }
        ],
        status_api_mock={
            "headers": {
                "Authorization": "Bearer IAM_TOKEN",
                "Accept": "application/json",
            }
        },
    )


def test_connector_init_csv(mocker, connector_init_csv_data, ansible_runner_ok):
    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = connector_init_csv_data.ams_events

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = connector_init_csv_data.iam_token

    statusapi_httpget = mocker.patch('argo_automation_cpas.statusapi.SessionWithRetry.http_get')
    statusapi_httpget.return_value = connector_init_csv_data.statusapi_jobs

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')

    webapi_fetchtopologyconfig = mocker.patch('argo_automation_cpas.webapi.WebAPI.fetch_topology_config')
    webapi_fetchtopologyconfig.return_value = connector_init_csv_data.webapi_topoconfig

    ansible_runner_run = mocker.patch('argo_automation_cpas.ansible.ansible_runner.run')
    ansible_runner_run.return_value = ansible_runner_ok

    app = Application()
    asyncio.run(app.run())

    assert webapi_fetchtopologyconfig.await_args_list[0] == mocker.call(
        connector_init_csv_data.topology_config_url,
        token=connector_init_csv_data.connector_token
    )

    assert statusapi_httpget.call_args_list[0] == mocker.call(
        connector_init_csv_data.status_url,
        **connector_init_csv_data.status_api_mock
    )

    assert statusapi_updatejobstatus.call_args_list[0] == mocker.call(
        connector_init_csv_data.tenant_id,
        connector_init_csv_data.event,
        'IN_PROGRESS',
        connector_init_csv_data.iam_token,
    )

    assert 'extravars' in ansible_runner_run.call_args_list[0][1]
    assert 'connector_tenants' in ansible_runner_run.\
        call_args_list[0][1]['extravars']
    assert ansible_runner_run.\
        call_args_list[0][1]['extravars']['connector_tenants'] == connector_init_csv_data.expected_connector_tenants

    assert statusapi_updatejobstatus.call_args_list[1] == mocker.call(
        connector_init_csv_data.tenant_id,
        connector_init_csv_data.event,
        'COMPLETED',
        connector_init_csv_data.iam_token,
        message=connector_init_csv_data.success_message
    )

    assert statusapi_updatejobstatus.call_count == 2


def test_connector_init_eosc_service_data(mocker, connector_init_eosc_service_data, ansible_runner_ok):
    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = connector_init_eosc_service_data.ams_events

    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = connector_init_eosc_service_data.iam_token

    session_httpget = mocker.patch('argo_automation_cpas.http.SessionWithRetry.http_get')
    session_httpget.side_effect = [
        connector_init_eosc_service_data.statusapi_jobs,
        connector_init_eosc_service_data.webapi_topoconfig,
    ]

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')

    ansible_runner_run = mocker.patch('argo_automation_cpas.ansible.ansible_runner.run')
    ansible_runner_run.return_value = ansible_runner_ok

    app = Application()
    asyncio.run(app.run())

    assert statusapi_updatejobstatus.call_args_list[0] == mocker.call(
        connector_init_eosc_service_data.tenant_id,
        connector_init_eosc_service_data.event,
        'IN_PROGRESS',
        connector_init_eosc_service_data.iam_token,
    )

    assert 'extravars' in ansible_runner_run.call_args_list[0][1]
    assert 'connector_tenants' in ansible_runner_run.\
        call_args_list[0][1]['extravars']
    assert ansible_runner_run.\
        call_args_list[0][1]['extravars']['connector_tenants'] == connector_init_eosc_service_data.expected_connector_tenants

    assert statusapi_updatejobstatus.call_args_list[1] == mocker.call(
        connector_init_eosc_service_data.tenant_id,
        connector_init_eosc_service_data.event,
        'COMPLETED',
        connector_init_eosc_service_data.iam_token,
        message=connector_init_eosc_service_data.success_message
    )

    assert statusapi_updatejobstatus.call_count == 2
