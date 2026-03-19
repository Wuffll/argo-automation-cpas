from argo_automation_cpas.config import get_settings


def test_default_settings() -> None:
    settings = get_settings()

    assert settings.base_url == "https://example.invalid"
    assert settings.verify_ssl is True
    assert settings.request_timeout == 30.0
