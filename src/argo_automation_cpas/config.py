from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


@dataclass(slots=True)
class Settings:
    base_url: str = os.getenv("ARGO_AUTOMATION_CPAS_BASE_URL", "https://example.invalid")
    verify_ssl: bool = _get_bool("ARGO_AUTOMATION_CPAS_VERIFY_SSL", True)
    request_timeout: float = _get_float("ARGO_AUTOMATION_CPAS_REQUEST_TIMEOUT", 30.0)
    ansible_private_data_dir: str = os.getenv("ARGO_AUTOMATION_CPAS_ANSIBLE_PRIVATE_DATA_DIR", "ansible")
    ansible_playbook: str = os.getenv("ARGO_AUTOMATION_CPAS_ANSIBLE_PLAYBOOK", "demo.yml")


def get_settings() -> Settings:
    return Settings()
