"""Focused tests for the rendered Compose log-retention verifier."""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
_spec = importlib.util.spec_from_file_location(
    "verify_compose_logging", os.path.join(SCRIPTS_DIR, "verify_compose_logging.py")
)
verify_compose_logging = importlib.util.module_from_spec(_spec)
sys.modules["verify_compose_logging"] = verify_compose_logging
_spec.loader.exec_module(verify_compose_logging)


def _payload(*, driver="json-file", max_size="20m", max_file="10"):
    return {
        "services": {
            "python-engine": {
                "logging": {"driver": driver, "options": {"max-size": max_size, "max-file": max_file}}
            }
        }
    }


def test_accepts_current_rendered_python_engine_log_contract():
    result = verify_compose_logging.assess_rendered_compose(_payload())
    assert result == {
        "service": "python-engine",
        "driver": "json-file",
        "max_size": "20m",
        "max_file": 10,
        "capacity_mib": 200,
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"services": {}}, "no 'python-engine' service"),
        (_payload(driver="local"), "driver must be 'json-file'"),
        (_payload(max_size="20"), "positive whole K/M/G"),
        (_payload(max_file="0"), "positive integer"),
        (_payload(max_size="10m", max_file="10"), "expected at least 200 MiB"),
    ],
)
def test_rejects_unsafe_or_unrendered_contract(payload, message):
    with pytest.raises(verify_compose_logging.ComposeLoggingError, match=message):
        verify_compose_logging.assess_rendered_compose(payload)


def test_main_renders_then_reports_only_logging_values(monkeypatch, capsys, tmp_path):
    commands = []

    class Completed:
        returncode = 0
        stdout = json.dumps(_payload())
        stderr = ""

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(verify_compose_logging.subprocess, "run", fake_run)
    assert verify_compose_logging.main(["--compose-file", str(tmp_path / "compose.yml")]) == 0
    assert commands[0][0][-2:] == ["--format", "json"]
    out = capsys.readouterr().out
    assert "capacity=200MiB" in out
    assert "environment" not in out.lower()


def test_main_fails_closed_when_compose_cannot_render(monkeypatch, capsys):
    class Completed:
        returncode = 1
        stdout = ""
        stderr = "invalid compose"

    monkeypatch.setattr(verify_compose_logging.subprocess, "run", lambda *args, **kwargs: Completed())
    assert verify_compose_logging.main([]) == 2
    assert "invalid compose" in capsys.readouterr().err
