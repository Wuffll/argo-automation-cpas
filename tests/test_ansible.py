import pytest
from unittest.mock import patch
from unittest.mock import MagicMock
import unittest


from argo_automation_cpas.ansible import *
import argo_automation_cpas.ansible


@pytest.mark.asyncio
async def test_ansible_run():
    with patch("argo_automation_cpas.ansible.ansible_runner.run") as mock_runner:
        mock_runner.return_value = {"status": "Mocked", "rc": 999}

        mock_runner.return_value = "MockRun"

        ansible = Ansible()
        output = await ansible.run("")

        print("Output = " + str(output))

        # Here you can test out whether ansible has everything set properly before the run
        # print(str(mock_runner.call_args.kwargs))

        mock_runner.assert_called_once()
