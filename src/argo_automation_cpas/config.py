import configparser
import os


CONFIG_ENV_VAR = "ARGO_CPAS_CONFIG"
DEFAULT_CONFIG_LOCATIONS = (
    "config/argo-cpas.conf",
    "/etc/argo-cpas.conf",
)
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_VERIFY_SSL = True
DEFAULT_ANSIBLE_PRIVATE_DATA_DIR = "ansible"
DEFAULT_ANSIBLE_PLAYBOOK = "init.yml"


class Section:
    def __init__(self, **values):
        self.__dict__.update(values)


class Settings:
    def __init__(self, path, parser):
        self.path = os.path.abspath(path)
        self.config_dir = os.path.dirname(self.path)
        self.venv = parser.defaults().get("venv", "")

        general = self._get_section(parser, "general")
        ams = self._get_section(parser, "ams")
        webapi = self._get_section(parser, "webapi")

        self.general = Section(
            loggers=self._split_csv(general.get("loggers", "")),
        )
        self.ams = Section(
            project=ams.get("project", ""),
            host=ams.get("host", ""),
            subscription=ams.get("subscription", ""),
            token=ams.get("token", ""),
            url=self._normalize_url(ams.get("host", "")),
        )
        self.webapi = Section(
            host=webapi.get("host", ""),
            url=self._normalize_url(webapi.get("host", "")),
        )

        self.base_url = self.webapi.url
        self.request_timeout = DEFAULT_REQUEST_TIMEOUT
        self.verify_ssl = DEFAULT_VERIFY_SSL
        self.ansible_private_data_dir = os.path.join(self.config_dir, "..", "ansible")
        self.ansible_private_data_dir = os.path.abspath(self.ansible_private_data_dir)
        self.ansible_playbook = DEFAULT_ANSIBLE_PLAYBOOK

    def _get_section(self, parser, section_name):
        if not parser.has_section(section_name):
            raise ValueError("Missing required section [%s] in %s" % (section_name, self.path))
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


def get_settings(path=None):
    return load_config(path)
