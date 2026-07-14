import asyncio
from dataclasses import dataclass

import pytest

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import load_config


TOPOLOGY_FEED_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1xiptZgYG2bn78hwBCEP7esTDyfMvvEXFLfJY2HblfI8/export?gid=0&format=csv"
)
TENANT_ID = "184da7ca-5a64-4810-aa39-18cfaddbd44b"
TENANT_NAME = "AUTOMATION"
CONNECTOR_EVENT = "INIT_TOPOLOGY_CONNECTOR"
IAM_TOKEN = "IAM_TOKEN"
CONNECTOR_TOKEN = "AUTOMATION-CONNECTOR"
SUCCESS_MESSAGE = (
    "Connector successfully configured for tenant AUTOMATION by argo-automation-cpas"
)


@dataclass(frozen=True)
class ConnectorInitData:
    iam_token: str = IAM_TOKEN
    tenant_id: str = TENANT_ID
    tenant_name: str = TENANT_NAME
    event: str = CONNECTOR_EVENT
    connector_token: str = CONNECTOR_TOKEN
    success_message: str = SUCCESS_MESSAGE
    topology_feed_url: str = TOPOLOGY_FEED_URL
    topology_config_url: str = "/api/v2/feeds/topology"

    @property
    def status_url(self):
        return (
            "https://API-STATUS_MON_ARGO/v1/automation/tenants/"
            f"{self.tenant_id}/status"
        )

    @property
    def ams_events(self):
        return [
            {
                "name": self.event,
                "properties": {
                    "tenant_id": self.tenant_id,
                    "tenant_name": self.tenant_name,
                },
                "created_at": "2026-04-04T09:05:28.607501253Z",
            }
        ]

    @property
    def statusapi_jobs(self):
        return {
            "name": self.tenant_name,
            "status": {
                "jobs": [
                    {
                        "name": self.event,
                        "status": "INITIALISED",
                        "start": None,
                        "end": None,
                        "message": "Waiting for manual administrator action",
                        "mode": "MANUAL",
                    }
                ]
            },
            "readiness": None,
        }

    @property
    def webapi_topoconfig(self):
        return {
            "connector_tenant_topo_type": "CSV",
            "connector_tenant_topo_feed": self.topology_feed_url,
            "paginated": "false",
            "fetch_type": [
                "ServiceGroups",
            ],
            "uid_endpoints": "",
        }

    @property
    def expected_connector_tenants(self):
        return [
            {
                "tenant_name": self.tenant_name,
                "tenant_topo_type": "CSV",
                "tenant_cron_weights_disable": True,
                "tenant_cron_downtimes_disable": True,
                "tenant_webapi_token": self.connector_token,
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
                "tenant_topo_feed": self.topology_feed_url,
            }
        ]

    @property
    def status_api_mock(self):
        return {
            "headers": {
                "Authorization": f"Bearer {self.iam_token}",
                "Accept": "application/json",
            }
        }


@dataclass(frozen=True)
class RunnerResult:
    status: str = "successful"
    rc: int = 0


@pytest.fixture
def cpas_test_settings(mocker):
    settings = load_config("tests/argo-cpas-tests.conf")
    mocker.patch('argo_automation_cpas.config._settings', new=settings)
    return settings


@pytest.fixture
def ansible_runner_ok():
    return RunnerResult()


@pytest.fixture
def connector_init_data():
    return ConnectorInitData()


def test_connector_init(mocker, cpas_test_settings, connector_init_data, ansible_runner_ok):
    ams_pull_messages = mocker.patch('argo_automation_cpas.ams.AMS.pull_messages')
    ams_pull_messages.return_value = connector_init_data.ams_events
    ams_has_sub = mocker.patch('argo_automation_cpas.ams.ArgoMessagingService.has_sub')
    ams_has_sub.return_value = True

    iam_fetchtoken = mocker.patch('argo_automation_cpas.iam.IAM.fetch_token')
    iam_fetchtoken.return_value = connector_init_data.iam_token

    statusapi_httpget = mocker.patch('argo_automation_cpas.statusapi.SessionWithRetry.http_get')
    statusapi_httpget.return_value = connector_init_data.statusapi_jobs

    statusapi_updatejobstatus = mocker.patch('argo_automation_cpas.statusapi.StatusAPI.update_job_status')
    webapi_fetchtopologyconfig = mocker.patch('argo_automation_cpas.webapi.WebAPI.fetch_topology_config')
    webapi_fetchtopologyconfig.return_value = connector_init_data.webapi_topoconfig

    ansible_runner_run = mocker.patch('argo_automation_cpas.ansible.ansible_runner.run')
    ansible_runner_run.return_value = ansible_runner_ok

    app = Application()
    asyncio.run(app.run())

    webapi_fetchtopologyconfig.assert_called_with(
        connector_init_data.topology_config_url,
        token=connector_init_data.connector_token
    )

    statusapi_httpget.assert_called_with(
        connector_init_data.status_url,
        **connector_init_data.status_api_mock
    )

    assert 'extravars' in ansible_runner_run.call_args_list[0][1]
    assert 'connector_tenants' in ansible_runner_run.\
        call_args_list[0][1]['extravars']
    assert ansible_runner_run.\
        call_args_list[0][1]['extravars']['connector_tenants'] == connector_init_data.expected_connector_tenants

    statusapi_updatejobstatus.assert_called_with(
        connector_init_data.tenant_id,
        connector_init_data.event,
        'COMPLETED',
        connector_init_data.iam_token,
        message=connector_init_data.success_message
    )
