import json
import re

import pytest

from bluepulse_backend import worker


def test_startup_settings_check_reports_active_services_and_budget(monkeypatch, capsys):
    monkeypatch.setenv("BLUEPULSE_COLLECT_ENABLED", "1")
    monkeypatch.setenv("BLUEPULSE_MODEL_CALLS_ENABLED", "1")
    monkeypatch.setenv("BLUEPULSE_MODEL_BUDGET_MINUTE", "10")
    monkeypatch.setenv("BLUEPULSE_MODEL_BUDGET_HOUR", "20")
    monkeypatch.setenv("BLUEPULSE_MODEL_BUDGET_DAY", "30")
    monkeypatch.setattr(worker, "load_local_credentials", lambda: ("https://model.example", "secret", "test"))
    monkeypatch.setattr(worker, "_run_daemon", lambda *args: pytest.fail("daemon started during preflight"))
    worker.main(["--check-config"])
    config = json.loads(capsys.readouterr().out)
    assert config["collection"] is True
    assert config["model_budget"] == {"minute": 10, "hour": 20, "day": 30}
    for key in ("collection_rule_version", "collection_entry_fingerprint", "database_fingerprint"):
        assert re.fullmatch(r"[0-9a-f]{64}", config[key])
    assert "secret" not in json.dumps(config)


def test_same_stem_databases_are_distinct_in_startup_configuration(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLUEPULSE_MODEL_CALLS_ENABLED", "0")
    configs = []
    for name in ("target.db", "target.sqlite3"):
        monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{(tmp_path / name).as_posix()}")
        worker.main(["--check-config"])
        configs.append(json.loads(capsys.readouterr().out))
    assert configs[0]["database_fingerprint"] != configs[1]["database_fingerprint"]
    assert configs[0]["collection_rule_version"] == configs[1]["collection_rule_version"]
    assert configs[0]["collection_entry_fingerprint"] == configs[1]["collection_entry_fingerprint"]
    assert list(tmp_path.iterdir()) == []


def test_readiness_ignores_stale_marker_and_checks_active_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{tmp_path / 'launch.db'}")
    config = {"collection": True, "model_budget": None}
    assert worker._worker_ready(config) is False
    with worker._daemon_lock() as handle:
        worker._write_worker_ready(handle, config)
        assert worker._worker_ready(config) is True
        assert worker._worker_ready({**config, "collection": False}) is False
    assert worker._worker_ready(config) is False
