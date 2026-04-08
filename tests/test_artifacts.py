import os

import pytest
from unittest.mock import MagicMock

from argo_automation_cpas.artifacts import (
    _filter_stdout,
    _role_of,
    clean_artifacts,
    print_artifacts,
)


# ---------------------------------------------------------------------------
# _role_of
# ---------------------------------------------------------------------------

def test_role_of_match():
    assert _role_of("TASK [connector : Install packages]") == "connector"


def test_role_of_no_match():
    assert _role_of("PLAY [all]") is None


def test_role_of_empty():
    assert _role_of("") is None


# ---------------------------------------------------------------------------
# _filter_stdout
# ---------------------------------------------------------------------------

SAMPLE_STDOUT = """\
PLAY [all]
TASK [connector : Install packages]
ok: [host1]
TASK [sensu : Configure checks]
changed: [host1]
TASK [connector : Start service]
ok: [host1]
PLAY RECAP"""


def test_filter_stdout_no_roles():
    assert _filter_stdout(SAMPLE_STDOUT, []) == SAMPLE_STDOUT


def test_filter_stdout_single_role():
    result = _filter_stdout(SAMPLE_STDOUT, ["connector"])
    assert "Install packages" in result
    assert "Start service" in result
    assert "Configure checks" not in result
    assert "PLAY [all]" in result
    assert "PLAY RECAP" in result


def test_filter_stdout_nonexistent_role():
    result = _filter_stdout(SAMPLE_STDOUT, ["unknown"])
    assert "Install packages" not in result
    assert "PLAY [all]" in result


# ---------------------------------------------------------------------------
# print_artifacts
# ---------------------------------------------------------------------------

def test_print_artifacts_all(capsys):
    runner = MagicMock()
    runner.stdout.read.return_value = "task output"
    runner.stderr.read.return_value = "error output"

    print_artifacts(runner, [])

    out = capsys.readouterr().out
    assert "task output" in out
    assert "error output" in out
    assert "STDOUT" in out
    assert "STDERR" in out


def test_print_artifacts_filtered(capsys):
    runner = MagicMock()
    runner.stdout.read.return_value = SAMPLE_STDOUT
    runner.stderr.read.return_value = ""

    print_artifacts(runner, ["connector"])

    out = capsys.readouterr().out
    assert "[roles: connector]" in out
    assert "Install packages" in out
    assert "Configure checks" not in out


def test_print_artifacts_empty(capsys):
    runner = MagicMock()
    runner.stdout.read.side_effect = Exception("no stdout")
    runner.stderr.read.side_effect = Exception("no stderr")

    print_artifacts(runner, [])

    out = capsys.readouterr().out
    assert "(empty)" in out


# ---------------------------------------------------------------------------
# clean_artifacts
# ---------------------------------------------------------------------------

def test_clean_artifacts_no_dir(tmp_path):
    clean_artifacts(str(tmp_path / "nonexistent"), [])


def test_clean_artifacts_all(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "run-1").mkdir()
    (artifacts / "run-2").mkdir()

    clean_artifacts(str(artifacts), [])

    assert artifacts.exists()
    assert list(artifacts.iterdir()) == []


def test_clean_artifacts_by_role(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    run1 = artifacts / "run-1"
    run1.mkdir()
    (run1 / "stdout").write_text("TASK [connector : Install packages]\nok: [host1]")

    run2 = artifacts / "run-2"
    run2.mkdir()
    (run2 / "stdout").write_text("TASK [sensu : Configure checks]\nchanged: [host1]")

    clean_artifacts(str(artifacts), ["connector"])

    assert not run1.exists()
    assert run2.exists()


def test_clean_artifacts_by_role_no_match(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    run1 = artifacts / "run-1"
    run1.mkdir()
    (run1 / "stdout").write_text("TASK [sensu : Configure checks]\nchanged: [host1]")

    clean_artifacts(str(artifacts), ["unknown"])

    assert run1.exists()
