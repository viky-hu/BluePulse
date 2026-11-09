from datetime import UTC, datetime
import json
import sqlite3

import httpx

from bluepulse_backend import runtime_health as health


def test_missing_database_does_not_create_anything(tmp_path):
    target = tmp_path / 'missing' / 'live.db'
    report = health.database_snapshot(target, datetime.now(UTC))
    assert report['status'] == 'unavailable'
    assert not target.parent.exists()


def test_snapshot_empty_and_repeated_are_healthy(tmp_path, monkeypatch):
    path = tmp_path / 'test.db'
    from bluepulse_backend.cli import initialize
    from bluepulse_backend.db import make_engine
    engine = make_engine(f'sqlite:///{path.as_posix()}')
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{path.as_posix()}")
    initialize()
    engine.dispose()
    before = path.read_bytes()
    report = health.database_snapshot(path, datetime.now(UTC))
    assert report['status'] == 'ok'
    assert report['materials']['total'] == 0
    assert path.read_bytes() == before


def test_model_probe_requires_exact_listed_model(tmp_path):
    config = tmp_path / '.env'
    config.write_text('base_url=https://example.test/v1\nkey=private-key\nllm_id=wanted\n')
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={'data': [{'id': 'other'}]})
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        report = health.model_configuration(config, probe=True, client=client)
    assert report['configuration'] == 'valid'
    assert report['availability'] == 'model_not_listed'
    assert [r.method for r in requests] == ['GET']
    assert requests[0].url.path == '/v1/models'
    assert 'private-key' not in json.dumps(report)


def test_offline_configuration_never_uses_transport(tmp_path):
    path = tmp_path / '.env'
    path.write_text('base_url=https://example.test/v1\nkey=secret\nllm_id=wanted\n')
    with httpx.Client(transport=httpx.MockTransport(lambda request: 1 / 0)) as client:
        assert health.model_configuration(path, client=client)['availability'] == 'not_probed'


def test_safe_provider_failure_classification():
    raw = json.dumps({'body': json.dumps({'error': {'code': 'sensitive_words_detected', 'message': 'private prompt'}})})
    assert health.provider_error('provider_http_400', raw) == 'sensitive_words_detected'
    assert health.provider_error('secret raw prompt', None) == 'other'


def test_stale_marker_is_not_ready(tmp_path):
    path = tmp_path / 'worker.lock'
    path.write_bytes(b'0' + json.dumps({'collection': True, 'model_budget': None}).encode())
    before = path.read_bytes()
    assert health.worker_status(path, {'collection': True, 'model_budget': None})['status'] == 'not_running'
    assert path.read_bytes() == before


def test_collection_metrics_staleness_and_provider_receipts(tmp_path, monkeypatch):
    from datetime import timedelta
    from bluepulse_backend.cli import initialize
    path = tmp_path / 'live.db'
    monkeypatch.setenv('BLUEPULSE_DATABASE_URL', f'sqlite:///{path.as_posix()}')
    initialize()
    now = datetime.now(UTC)
    date = lambda value: value.replace(tzinfo=None).isoformat(' ')
    with sqlite3.connect(path) as db:
        source = db.execute('SELECT id FROM sources LIMIT 1').fetchone()[0]
        db.execute('UPDATE sources SET enabled=0')
        db.execute('UPDATE sources SET enabled=1,next_fetch_at=? WHERE id=?', (date(now + timedelta(hours=1)), source))
        db.execute('INSERT INTO source_runs(id,source_id,started_at,finished_at,status,candidate_count,fetch_metrics) VALUES(?,?,?,?,?,?,?)',
                   ('run', source, date(now), date(now), 'completed', 20, json.dumps({'added': 0, 'duplicates': 20})))
        db.commit()
    before = path.read_bytes()
    report = health.database_snapshot(path, now)
    active = next(item for item in report['sources'] if item['status'] != 'disabled')
    assert active['status'] == 'ok'
    assert active['new'] == 0 and active['repeated'] == 20
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        db.execute('UPDATE sources SET next_fetch_at=? WHERE id=?', (date(now - timedelta(days=2)), source))
        db.commit()
    report = health.database_snapshot(path, now)
    assert next(item for item in report['sources'] if item['slug'] == active['slug'])['status'] == 'stale'


def test_provider_unavailable_is_separate_from_valid_file(tmp_path):
    path = tmp_path / '.env'
    path.write_text('base_url=https://example.test/v1\nkey=secret\nllm_id=wanted\n')
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))) as client:
        report = health.model_configuration(path, probe=True, client=client)
    assert report == {'configuration': 'valid', 'availability': 'provider_unavailable'}

def test_held_worker_lock_exposes_only_safe_actual_configuration(tmp_path, monkeypatch):
    import errno
    import os
    path = tmp_path / 'worker.lock'
    observed = {'collection': False, 'model_budget': {'minute': 2, 'hour': 3, 'day': 4}}
    path.write_bytes(b'0' + json.dumps({**observed, 'extra': 'private'}).encode())
    def held(*args):
        raise OSError(errno.EACCES, 'locked')
    if os.name == 'nt':
        import msvcrt
        monkeypatch.setattr(msvcrt, 'locking', held)
    else:
        import fcntl
        monkeypatch.setattr(fcntl, 'flock', held)
    before = path.read_bytes()
    result = health.worker_status(path, {'collection': True, 'model_budget': None})
    assert result == {'status': 'configuration_mismatch', 'observed_configuration': observed}
    assert path.read_bytes() == before


def test_audit_requested_flags_do_not_override_actual_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPULSE_DATABASE_URL', f'sqlite:///{(tmp_path / "missing.db").as_posix()}')
    monkeypatch.setenv('BLUEPULSE_COLLECT_ENABLED', '1')
    monkeypatch.setenv('BLUEPULSE_MODEL_CALLS_ENABLED', '0')
    actual = {'collection': False, 'model_budget': None}
    monkeypatch.setattr(health, 'worker_status', lambda *args: {'status': 'configuration_mismatch', 'observed_configuration': actual})
    report = health.audit(check_services=False)
    assert report['requested_worker_configuration']['collection'] is True
    assert report['actual_worker_configuration'] == actual
    assert report['collection'] == 'paused'


def test_paid_http_success_timestamp_does_not_use_later_failed_attempt(tmp_path, monkeypatch):
    from datetime import timedelta
    from bluepulse_backend.cli import initialize
    path = tmp_path / 'paid.db'
    monkeypatch.setenv('BLUEPULSE_DATABASE_URL', f'sqlite:///{path.as_posix()}')
    initialize()
    now = datetime.now(UTC)
    success = now - timedelta(hours=2)
    date = lambda value: value.replace(tzinfo=None).isoformat(' ')
    with sqlite3.connect(path) as db:
        for number, at, status in ((1, success, 200), (2, now, 400)):
            db.execute('INSERT INTO paid_receipts(key,subject,purpose,request,status,updated_at,latest_attempt,auto_released) VALUES(?,?,?,?,?,?,?,?)',
                       (str(number), 'subject', 'analyze', '{}', 'received', date(at), 1, 0))
            body = {'error': {'code': 'sensitive_words_detected', 'message': 'private prompt'}} if status == 400 else {'choices': []}
            db.execute('INSERT INTO paid_attempts(receipt_key,number,service,sent_at,finished_at,status,response) VALUES(?,?,?,?,?,?,?)',
                       (str(number), 1, 'example.test', date(at), date(at), 'received', json.dumps({'status': status, 'body': json.dumps(body)})))
        db.commit()
    report = health.database_snapshot(path, now)
    assert report['paid_response_status'] == {'200': 1, '400': 1}
    assert report['last_http_200_at'] == success.isoformat()
    assert report['last_attempt_at'] == now.isoformat()
    assert report['latest_paid_failures'] == [{'sent_at': now.isoformat(), 'code': 'sensitive_words_detected'}]
    assert 'private prompt' not in json.dumps(report)
    assert health.provider_error('robots_timeout') == 'robots_timeout'
