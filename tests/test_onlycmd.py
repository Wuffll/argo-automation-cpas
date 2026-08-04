import pytest
import asyncio

from argo_automation_cpas.app import Application
from argo_automation_cpas.config import load_config


@pytest.fixture(autouse=True)
def cpas_test_settings(mocker):
    settings = load_config("tests/argo-cpas-tests.conf")
    mocker.patch('argo_automation_cpas.config._settings', new=settings)
    return settings


def test_onlyams_tenant_with_cached_tokens(mocker):
    app = Application()

    app.only_ams = True
    app.add_tenants = ["SRCE"]
    mocker.patch('argo_automation_cpas.ams.ArgoMessagingService')
    ams_httpost = mocker.patch('argo_automation_cpas.tokens.SessionWithRetry.http_post')

    asyncio.run(app.run())

    assert not ams_httpost.called


def test_onlyams_tenant_without_tokens(mocker):
    app = Application()

    app.only_ams = True
    app.add_tenants = ["NEWTENANT"]
    mocker.patch('argo_automation_cpas.ams.ArgoMessagingService')
    ams_httpost = mocker.patch('argo_automation_cpas.tokens.SessionWithRetry.http_post')
    ams_httpost = mocker.patch('argo_automation_cpas.tokens.SessionWithRetry.http_post')
    mock_savetokens = mocker.patch('argo_automation_cpas.tokens.ComponentTokens.save_tokens')

    ams_httpost.side_effect = [
        dict(data={'api_key': 'TOKEN1'}),
        dict(data={'api_key': 'TOKEN2'}),
    ]

    asyncio.run(app.run())

    assert ams_httpost.called
    assert ams_httpost.call_count == 2
    assert ams_httpost.call_args_list[0][0][0] == \
        '/v1/integrations/argo-monbox/by-project-name/NEWTENANT/refresh'
    assert ams_httpost.call_args_list[1][0][0] == \
        '/v1/integrations/argo-archiver/by-project-name/NEWTENANT/refresh'

    assert mock_savetokens.called
    assert mock_savetokens.call_count == 1
    assert mock_savetokens.call_args_list[0] == mocker.call(
        {
            'SRCE': {
                'argo-monbox': 'SRCE-ARGOMONBOX',
                'argo-archiver': 'SRCE-ARGOARCHIVER'
            },
            'AUTOMATION': {
                'argo-monbox': 'AUTOMATION-ARGOMONBOX',
                'argo-archiver': 'AUTOMATION-ARGOARCHIVER'
            },
            'INSTRUCT-ERIC': {
                'argo-monbox': 'INSTRUCT-ERIC-ARGOMONBOX',
                'argo-archiver': 'INSTRUCT-ERIC-ARGOARCHIVER'
            },
            'NEWTENANT': {
                'argo-monbox': 'TOKEN1',
                'argo-archiver': 'TOKEN2'
            }
        },
        'tests/tokens_ams.json'
    )
