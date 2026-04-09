import os

import pytest
import yaml

from argo_automation_cpas.config import load_config, _resolve_config_path, CONFIG_ENV_VAR


FULL_CONFIG = """\
[DEFAULT]
VENV = /opt/argo-automation-cpas/

[general]
loggers = stdout, file, syslog
log_level = INFO
log_file = %(VENV)svar/log/argo-cpas.log
syslog_address = /dev/log
syslog_facility = user

[automation]
tenants = TENANT-A, TENANT-B

[ams]
project = ARGO-MON-AUTOMATION
host = api.devel.msg.argo.grnet.gr
subscription = events-sub-2
token = AUTOMATION_TOKEN

[webapi]
host = api.devel.mon.argo.grnet.gr
url_api_config = /api/v2/feeds/topology
url_api_integrations = /api/v3/integrations/components/{component}/by-tenant-name/{tenant_name}/refresh
token_component_admin = t0k3n
components = monbox, sensu, connectors

[statusapi]
api = https://api-status.devel.mon.argo.grnet.gr/v1/automation/tenants/{tenant_id}/status

[iam]
api = https://login-devel.einfra.grnet.gr/auth/realms/einfra/protocol/openid-connect/token
oidc_client_id = client-id
oidc_client_secret = client-secret

[ansible]
user_connector = user
group_connector = user
ssh_private_key = /home/user/.ssh/sshkey
defaults_file = %(VENV)setc/roles-defaults.yml
tokens_manual = %(VENV)setc/tokens.yml
connectors_playbook = connectors.yml
connectors_inventory = connectors.ini
"""


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "argo-cpas.conf"
    path.write_text(FULL_CONFIG)
    return str(path)


# ---------------------------------------------------------------------------
# general
# ---------------------------------------------------------------------------

def test_general_section(config_file):
    s = load_config(config_file)
    assert s.general.loggers == ["stdout", "file", "syslog"]
    assert s.general.log_level == 20  # logging.INFO
    assert s.general.log_file == "/opt/argo-automation-cpas/var/log/argo-cpas.log"
    assert s.general.syslog_address == "/dev/log"


# ---------------------------------------------------------------------------
# automation
# ---------------------------------------------------------------------------

def test_automation_section(config_file):
    s = load_config(config_file)
    assert s.automation.tenants == ["TENANT-A", "TENANT-B"]


# ---------------------------------------------------------------------------
# ams
# ---------------------------------------------------------------------------

def test_ams_section(config_file):
    s = load_config(config_file)
    assert s.ams.project == "ARGO-MON-AUTOMATION"
    assert s.ams.host == "api.devel.msg.argo.grnet.gr"
    assert s.ams.subscription == "events-sub-2"
    assert s.ams.token == "AUTOMATION_TOKEN"
    assert s.ams.url == "https://api.devel.msg.argo.grnet.gr"


# ---------------------------------------------------------------------------
# webapi
# ---------------------------------------------------------------------------

def test_webapi_section(config_file):
    s = load_config(config_file)
    assert s.webapi.host == "api.devel.mon.argo.grnet.gr"
    assert s.webapi.url == "https://api.devel.mon.argo.grnet.gr"
    assert s.webapi.url_api_config == "/api/v2/feeds/topology"
    assert "{component}" in s.webapi.url_api_integrations
    assert s.webapi.token_component_admin == "t0k3n"
    assert s.webapi.components == ["monbox", "sensu", "connectors"]
    assert s.webapi.tokens_spool.endswith("var/spool/webapi_tokens.json")


# ---------------------------------------------------------------------------
# statusapi
# ---------------------------------------------------------------------------

def test_statusapi_section(config_file):
    s = load_config(config_file)
    assert "{tenant_id}" in s.statusapi.api


# ---------------------------------------------------------------------------
# iam
# ---------------------------------------------------------------------------

def test_iam_section(config_file):
    s = load_config(config_file)
    assert "openid-connect/token" in s.iam.api
    assert s.iam.oidc_client_id == "client-id"
    assert s.iam.oidc_client_secret == "client-secret"
    assert s.iam.token_spool.endswith("var/spool/iam_access.yml")


# ---------------------------------------------------------------------------
# ansible
# ---------------------------------------------------------------------------

def test_ansible_section(config_file):
    s = load_config(config_file)
    assert s.ansible.user_connector == "user"
    assert s.ansible.group_connector == "user"
    assert s.ansible.ssh_private_key == "/home/user/.ssh/sshkey"
    assert s.ansible.defaults_file.endswith("etc/roles-defaults.yml")
    assert s.ansible.connectors_playbook == "connectors.yml"
    assert s.ansible.connectors_inventory == "connectors.ini"


def test_ansible_defaults_loading(tmp_path):
    defaults = {"connector_tenant_topo_type": "CSV", "connector_tenant_bdii": False}
    defaults_file = tmp_path / "roles-defaults.yml"
    defaults_file.write_text(yaml.dump(defaults))

    tokens_file = tmp_path / "tokens.yml"
    tokens_file.write_text(yaml.dump({"connector_tokens": {"EGI": "tok-egi"}}))

    config_text = FULL_CONFIG.replace(
        "%(VENV)setc/roles-defaults.yml", str(defaults_file)
    ).replace(
        "%(VENV)setc/tokens.yml", str(tokens_file)
    )
    config_path = tmp_path / "argo-cpas.conf"
    config_path.write_text(config_text)

    s = load_config(str(config_path))
    assert s.ansible.defaults["connector_tenant_topo_type"] == "CSV"
    assert s.ansible.defaults["connector_tenant_bdii"] is False
    assert s.ansible.tokens == {"EGI": "tok-egi"}


# ---------------------------------------------------------------------------
# top-level attributes
# ---------------------------------------------------------------------------

def test_top_level_attributes(config_file):
    s = load_config(config_file)
    assert s.venv == "/opt/argo-automation-cpas"
    assert s.base_url == s.webapi.url
    assert s.request_timeout == 30.0
    assert s.verify_ssl is True
    assert s.ansible_playbook == "init.yml"
    assert s.ansible_private_data_dir.endswith("ansible")


# ---------------------------------------------------------------------------
# _resolve_config_path
# ---------------------------------------------------------------------------

def test_resolve_config_path_explicit(config_file):
    assert _resolve_config_path(config_file) == config_file


def test_resolve_config_path_env_var(config_file, monkeypatch):
    monkeypatch.setenv(CONFIG_ENV_VAR, config_file)
    assert _resolve_config_path() == config_file


def test_resolve_config_path_missing():
    with pytest.raises(FileNotFoundError):
        _resolve_config_path("/nonexistent/path.conf")


# ---------------------------------------------------------------------------
# missing required section
# ---------------------------------------------------------------------------

def test_missing_required_section(tmp_path):
    config_path = tmp_path / "bad.conf"
    config_path.write_text("[DEFAULT]\nVENV = /opt/test/\n\n[general]\nloggers = stdout\n")

    with pytest.raises(ValueError, match="automation"):
        load_config(str(config_path))
