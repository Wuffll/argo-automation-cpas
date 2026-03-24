from argo_automation_cpas.config import load_config


def test_load_config_parses_template_shape(tmp_path):
    config_file = tmp_path / "argo-cpas.conf"
    config_file.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "VENV = /opt/argo-automation-cpas/",
                "",
                "[general]",
                "loggers = stdout, file, syslog",
                "",
                "[ams]",
                "project = ARGO-MON-AUTOMATION",
                "host = api.devel.msg.argo.grnet.gr",
                "subscription = events-sub-2",
                "token = AUTOMATION_TOKEN",
                "",
                "[webapi]",
                "host = api.devel.mon.argo.grnet.gr",
            ]
        )
    )

    settings = load_config(str(config_file))

    assert settings.venv == "/opt/argo-automation-cpas/"
    assert settings.general.loggers == ["stdout", "file", "syslog"]
    assert settings.ams.project == "ARGO-MON-AUTOMATION"
    assert settings.ams.host == "api.devel.msg.argo.grnet.gr"
    assert settings.ams.subscription == "events-sub-2"
    assert settings.ams.token == "AUTOMATION_TOKEN"
    assert settings.ams.url == "https://api.devel.msg.argo.grnet.gr"
    assert settings.webapi.host == "api.devel.mon.argo.grnet.gr"
    assert settings.webapi.url == "https://api.devel.mon.argo.grnet.gr"
    assert settings.base_url == settings.webapi.url
    assert settings.ansible_playbook == "init.yml"
