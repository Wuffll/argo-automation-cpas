import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--ansible-run", action="store_true", default=False, help="Initiate Ansible run from tests"
    )


@pytest.fixture
def ansiblerun(request):
    return request.config.getoption("--ansible-run")
