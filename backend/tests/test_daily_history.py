from datetime import UTC, date, datetime

from test_editions import db, report
from bluepulse_backend import admin_models  # Register the CLI audit table in the shared fixture.
from bluepulse_backend.daily_reports import compose_daily, compose_due_reports, prepare_daily
from bluepulse_backend.edition_models import DailyIssue, DailyIssueRevision


NOW = datetime(2026, 11, 15, 9, tzinfo=UTC)


def ids(content):
    return {row['itemId'] for row in content['main'] + content['flashes']}


def test_history_uses_source_date_for_old_first_import_and_preserves_gates(db, report):
    at = datetime(2026, 11, 1, 12, tzinfo=UTC)
    old, *_ = report(at, released=NOW)
    old.first_seen_at = NOW
    old.timeline_kind, old.backfill_reason = 'historical', 'first-import'
    stale, *_ = report(at, released=NOW)
    stale.editorial_revision = None
    hidden, *_ = report(at, released=NOW)
    hidden.withdrawn = True
    db.commit()
    content, _ = prepare_daily(db, '2026-11-02', NOW, historical_source_dates=True)
    assert ids(content) == {old.id}
    assert content['generator']['pendingReports'] == 1
    assert content['coverageNote'] == '1 篇稿件仍待处理或公开。'
    assert content['generator']['coverageMeasured'] is False


def test_history_respects_eight_am_boundary_date_only_and_unknown(db, report):
    before, *_ = report(datetime(2026, 11, 1, 23, 59, tzinfo=UTC))
    boundary, *_ = report(datetime(2026, 11, 2, tzinfo=UTC))
    day, *_ = report(datetime(2026, 11, 1, 1, tzinfo=UTC))
    day.published_at, day.published_date = None, date(2026, 11, 1)
    unknown, *_ = report(datetime(2026, 11, 1, 2, tzinfo=UTC))
    unknown.published_at, unknown.published_date, unknown.timeline_kind = None, None, 'unknown'
    db.commit()
    content, _ = prepare_daily(db, '2026-11-02', NOW, historical_source_dates=True)
    assert ids(content) == {before.id, day.id}
    content, _ = prepare_daily(db, '2026-11-03', NOW, historical_source_dates=True)
    assert ids(content) == {boundary.id}


def test_history_moves_old_citation_and_keeps_versions_without_duplicates(db, report):
    from bluepulse_backend.models import SourceRun

    item, source, *_ = report(datetime(2026, 11, 1, 12, tzinfo=UTC))
    item.first_seen_at = datetime(2026, 11, 8, 12, tzinfo=UTC)
    db.add(SourceRun(source_id=source.id, status='completed', started_at=item.first_seen_at,
                     finished_at=item.first_seen_at))
    # A legacy first-seen issue exists before the historical reconstruction.
    db.commit()
    compose_daily(db, '2026-11-09', now=NOW)
    assert ids(db.get(DailyIssue, '2026-11-09').content) == {item.id}
    for key in ('2026-11-02', '2026-11-09'):
        compose_daily(db, key, now=NOW, historical_source_dates=True, reason='历史归期', actor='maintenance')
    assert ids(db.get(DailyIssue, '2026-11-02').content) == {item.id}
    assert not ids(db.get(DailyIssue, '2026-11-09').content)
    old = db.get(DailyIssueRevision, ('2026-11-09', 1))
    assert ids(old.content) == {item.id}
    for key in ('2026-11-02', '2026-11-09'):
        assert not compose_daily(db, key, now=NOW, historical_source_dates=True,
                                 reason='历史归期', actor='maintenance')['written']


def test_worker_refresh_keeps_history_mode_and_resolves_old_pending(db, report):
    item, *_ = report(datetime(2026, 11, 1, 12, tzinfo=UTC), released=NOW)
    item.first_seen_at, item.editorial_revision = NOW, None
    item.timeline_kind, item.backfill_reason = 'historical', 'first-import'
    db.commit()
    compose_daily(db, '2026-11-02', now=NOW, historical_source_dates=True)
    assert db.get(DailyIssue, '2026-11-02').content['generator']['pendingReports'] == 1
    item.editorial_revision = item.revision
    db.commit()
    compose_due_reports(db, NOW, limit=30)
    issue = db.get(DailyIssue, '2026-11-02')
    assert ids(issue.content) == {item.id}
    assert issue.content['generator']['inputMode'] == 'source-date-history'
    assert issue.content['generator']['pendingReports'] == 0
    # A future ordinary issue must not inherit historical mode.
    assert 'inputMode' not in db.get(DailyIssue, '2026-11-15').content['generator']


def test_history_cli_preview_is_read_only_and_matches_sequential_execution(db, report, tmp_path, monkeypatch, capsys):
    import json
    import sqlite3
    from sqlalchemy import create_engine
    from bluepulse_backend import cli

    first, source, story, fact = report(datetime(2026, 11, 1, 12, tzinfo=UTC))
    report(datetime(2026, 11, 2, 12, tzinfo=UTC), source=source, story=story, fact=fact)
    path = tmp_path / 'business.db'
    with sqlite3.connect(path) as target:
        db.connection().connection.driver_connection.backup(target)
    monkeypatch.setattr(cli, '_database_file', lambda: path)
    monkeypatch.setattr(cli, 'make_engine', lambda: create_engine(f'sqlite:///{path.as_posix()}'))
    options = dict(start=date(2026, 11, 2), end=date(2026, 11, 3), historical_source_dates=True)
    cli.daily_range(**options, execute=False, reason=None)
    preview = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row['main'] for row in preview] == [1, 0]
    with sqlite3.connect(path) as connection:
        assert connection.execute('select count(*) from daily_issues').fetchone()[0] == 0
    cli.daily_range(**options, execute=True, reason='历史归期')
    result = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row['entries'] for row in result] == [row['main'] for row in preview]
