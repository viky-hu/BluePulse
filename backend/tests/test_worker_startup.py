import json

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
    assert json.loads(capsys.readouterr().out) == {
        "collection": True, "model_budget": {"minute": 10, "hour": 20, "day": 30},
    }


def test_readiness_ignores_stale_marker_and_checks_active_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{tmp_path / 'launch.db'}")
    config = {"collection": True, "model_budget": None}
    assert worker._worker_ready(config) is False
    with worker._daemon_lock() as handle:
        worker._write_worker_ready(handle, config)
        assert worker._worker_ready(config) is True
        assert worker._worker_ready({**config, "collection": False}) is False
    assert worker._worker_ready(config) is False
