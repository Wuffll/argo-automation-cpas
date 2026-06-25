import configparser
import logging
import logging.handlers
import os

import yaml

LOG = logging.getLogger(__name__)

CONFIG_ENV_VAR = "ARGO_CPAS_CONFIG"
DEFAULT_VENV = "/opt/argo-automation-cpas"
DEFAULT_CONFIG_LOCATIONS = (
    os.path.join(DEFAULT_VENV, "etc", "argo-cpas.conf"),
    "/etc/argo-cpas.conf",
)
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_VERIFY_SSL = True
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_DAEMON_SLEEP = 60
DEFAULT_ANSIBLE_PLAYBOOK = "init.yml"
DEFAULT_POEM_RESTAPI_TOKEN = os.path.join(
    DEFAULT_VENV, "var", "spool", "restapi_tokens.json"
)

_SYSLOG_FACILITIES = {
    name.lower().removeprefix("log_"): getattr(logging.handlers.SysLogHandler, name)
    for name in dir(logging.handlers.SysLogHandler)
    if name.startswith("LOG_")
}


class Section:
    def __init__(self, **values):
        self.__dict__.update(values)


class Settings:
    def __init__(self, path, parser):
        self.path = os.path.abspath(path)
        self.config_dir = os.path.dirname(self.path)
        self.venv = parser.defaults().get("venv", DEFAULT_VENV).rstrip("/")

        general = self._get_section(parser, "general")
        automation = self._get_section(parser, "automation")
        ams = self._get_section(parser, "ams")
        webapi = self._get_section(parser, "webapi")
        iam = self._get_section(parser, "iam")
        statusapi = self._get_section(parser, "statusapi")
        ansible = self._get_section(parser, "ansible")
        monboxgit = self._get_section(parser, "monboxgit")

        self.automation = Section(
            tenants=self._split_csv(automation.get("tenants", "")),
            filter_tenants=self._split_csv(automation.get("filter_tenants", "")),
        )
        self.general = Section(
            loggers=self._split_csv(general.get("loggers", "")),
            log_level=self._parse_log_level(general.get("log_level", "INFO")),
            log_file=general.get(
                "log_file", os.path.join(self.venv, "var", "log", "argo-cpas.log")
            ),
            syslog_address=general.get("syslog_address", "/dev/log"),
            syslog_facility=self._parse_syslog_facility(
                general.get("syslog_facility", "user")
            ),
            request_timeout=general.getfloat(
                "request_timeout", DEFAULT_REQUEST_TIMEOUT
            ),
            verify_ssl=general.getboolean("verify_ssl", DEFAULT_VERIFY_SSL),
            retries=general.getint("retries", DEFAULT_RETRIES),
            retry_delay=general.getfloat("retry_delay", DEFAULT_RETRY_DELAY),
            strip_ansi=general.getboolean("strip_ansi", True),
            daemon_sleep=general.getint("daemon_sleep", DEFAULT_DAEMON_SLEEP),
        )
        self.ams = Section(
            project=ams.get("project", ""),
            host=ams.get("host", ""),
            url=self._normalize_url(ams.get("host", "")),
            subscription=ams.get("subscription", ""),
            token=ams.get("token", ""),
            url_api_integrations=ams.get("url_api_integrations", ""),
            token_component_admin=ams.get("token_component_admin", ""),
            components=self._split_csv(ams.get("components", "")),
            pullmsgs=int(ams.get("pullmsgs", "1")),
            ack=ams.getboolean("ack", False),
            return_immediately=ams.getboolean("return_immediately", True),
            events=self._split_csv(ams.get("events", "INIT_TOPOLOGY_CONNECTOR")),
            tokens_spool=ams.get("tokens_spool", ""),
        )
        self.webapi = Section(
            host=webapi.get("host", ""),
            url=self._normalize_url(webapi.get("host", "")),
            url_api_config=webapi.get("url_api_config", ""),
            url_api_integrations=webapi.get("url_api_integrations", ""),
            token_component_admin=webapi.get("token_component_admin", ""),
            components=self._split_csv(webapi.get("components", "")),
            tokens_spool=webapi.get("tokens_spool", ""),
        )
        self.iam = Section(
            api=iam.get("api", ""),
            oidc_client_id=iam.get("oidc_client_id", ""),
            oidc_client_secret=iam.get("oidc_client_secret", ""),
            token_spool=iam.get("token_spool", ""),
        )
        self.statusapi = Section(api=statusapi.get("api", ""))

        self.monboxgit = Section(
            git_repo_owner=monboxgit.get("git_repo_owner", ""),
            git_repo_name=monboxgit.get("git_repo_name", ""),
            git_ssh_key_path=monboxgit.get("git_ssh_key_path", ""),
            git_branch_backend=monboxgit.get("git_branch_backend", ""),
            backend_config_file_path=monboxgit.get("backend_config_file_path", ""),
            git_branch_agent=monboxgit.get("git_branch_agent", ""),
            agent_config_file_path=monboxgit.get("agent_config_file_path", ""),
            init_check_count=monboxgit.getint("init_check_count", 10),
            init_check_interval=monboxgit.getint("init_check_interval", 150),
        )

        defaults_file = ansible.get("defaults_file", "")
        if defaults_file and not os.path.isabs(defaults_file):
            defaults_file = os.path.join(self.config_dir, defaults_file)

        tokens_file = ansible.get("tokens_manual", "")
        if tokens_file and not os.path.isabs(tokens_file):
            tokens_file = os.path.join(self.config_dir, tokens_file)

        poem_restapi_token = ansible.get(
            "poem_restapi_token", DEFAULT_POEM_RESTAPI_TOKEN
        )
        if poem_restapi_token and not os.path.isabs(poem_restapi_token):
            poem_restapi_token = os.path.join(self.config_dir, poem_restapi_token)

        self.ansible = Section(
            user_connector=ansible.get("user_connector", ""),
            group_connector=ansible.get("group_connector", ""),
            ssh_private_key=ansible.get("ssh_private_key", ""),
            defaults_file=defaults_file,
            defaults=self._load_ansible_defaults(defaults_file),
            tokens_file=tokens_file,
            tokens=self._load_connector_tokens(tokens_file),
            connectors_playbook=ansible.get("connectors_playbook", "connectors.yml"),
            connectors_inventory=ansible.get("connectors_inventory", "connectors.ini"),
            poem_playbook=ansible.get("poem_playbook", "poem.yml"),
            poem_inventory=ansible.get("poem_inventory", "poem.ini"),
            poem_fqdn_suffix=ansible.get("poem_fqdn_suffix", "fqdn.suffix"),
            poem_restapi_token=poem_restapi_token,
            poem_superuserpassword=ansible.get("poem_superuserpassword", ""),
            user_sensu=ansible.get("user_sensu", ""),
            sensu_inventory=ansible.get("sensu_inventory", "sensu.ini"),
        )

        self.base_url = self.webapi.url
        self.ansible_private_data_dir = os.path.join(self.venv, "ansible")
        self.ansible_playbook = DEFAULT_ANSIBLE_PLAYBOOK

    def _get_section(self, parser, section_name):
        if not parser.has_section(section_name):
            raise ValueError(
                "Missing required section [%s] in %s" % (section_name, self.path)
            )
        return parser[section_name]

    def _normalize_url(self, value):
        value = value.strip()
        if not value:
            return ""
        if "://" in value:
            return value.rstrip("/")
        return "https://%s" % value.rstrip("/")

    def _split_csv(self, value):
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _parse_log_level(self, value):
        level = logging.getLevelName(value.upper())
        if not isinstance(level, int):
            raise ValueError("Unknown log_level %r in %s" % (value, self.path))
        return level

    def _load_yaml_mapping(self, path, label):
        if not path:
            return {}
        if not os.path.exists(path):
            LOG.warning("%s not found: %s", label, path)
            return {}
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError("%s must be a YAML mapping: %s" % (label, path))
        return data

    def _load_ansible_defaults(self, path):
        return self._load_yaml_mapping(path, "ansible defaults_file")

    def _load_connector_tokens(self, path):
        data = self._load_yaml_mapping(path, "ansible tokens_file")
        tokens = data.get("connector_tokens", {})
        if not isinstance(tokens, dict):
            raise ValueError("connector_tokens in %s must be a mapping" % path)
        return tokens

    def _parse_syslog_facility(self, value):
        key = value.lower().removeprefix("log_")
        if key not in _SYSLOG_FACILITIES:
            raise ValueError(
                "Unknown syslog_facility %r in %s. Supported: %s"
                % (value, self.path, ", ".join(sorted(_SYSLOG_FACILITIES)))
            )
        return _SYSLOG_FACILITIES[key]


def _resolve_config_path(path=None):
    candidates = []

    if path:
        candidates.append(path)

    env_path = os.getenv(CONFIG_ENV_VAR)
    if env_path:
        candidates.append(env_path)

    candidates.extend(DEFAULT_CONFIG_LOCATIONS)

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "Could not find a configuration file. Checked: %s"
        % ", ".join(os.path.abspath(candidate) for candidate in candidates if candidate)
    )


def load_config(path=None):
    config_path = _resolve_config_path(path)
    parser = configparser.ConfigParser()
    parser.read(config_path)
    return Settings(config_path, parser)


_settings = None


def get_settings(path=None):
    global _settings
    if _settings is None:
        _settings = load_config(path)
    return _settings
