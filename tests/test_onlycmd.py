import pytest
import asyncio


from argo_automation_cpas.app import Application


def test_onlyams(mocker):
    app = Application()

    app.only_ams = True
    app.add_tenants = "SRCE"
    mocker.patch('argo_automation_cpas.ams.AMS.pull_and_print')

    asyncio.run(app.run())
