import pytest

from argo_automation_cpas.log import setup_logging


setup_logging()


def pytest_addoption(parser):
    parser.addoption(
        "--ansible-run", action="store_true", default=False, help="Initiate Ansible run from tests"
    )


@pytest.fixture
def ansiblerun(request):
    return request.config.getoption("--ansible-run")
