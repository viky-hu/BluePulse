"""Read-only runtime/content audit. Never initializes storage or generates model output."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime, timedelta
import errno
import json
import os
from pathlib import Path
import re
import sqlite3

import httpx

from .collection_version import IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS, sqlite_database_path, worker_configuration
from .db import database_url
from .live_model import DEFAULT_MODEL_ENV, load_local_credentials


def _time(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def provider_error(code, response=None):
    # Only return a fixed vocabulary, never provider messages, prompts or credentials.
    if response:
        try:
            envelope = json.loads(response) if isinstance(response, str) else response
            body = envelope.get('body', {})
            body = json.loads(body) if isinstance(body, str) else body
            error = body.get('error', {}) if isinstance(body, dict) else {}
            if isinstance(error, dict) and error.get('code') == 'sensitive_words_detected':
                return 'sensitive_words_detected'
        except (ValueError, TypeError, AttributeError):
            pass
    if code and re.fullmatch(r'(?:(?:provider|robots)_)?http_[0-9]{3}', code):
        return code
    allowed = {'receipt_unknown', 'provider_timeout_unknown', 'provider_transport_unknown',
               'provider_invalid_json', 'provider_invalid_schema', 'provider_output_truncated',
               'provider_empty_content', 'worker_interrupted', 'sensitive_words_detected',
               'request_budget_60', 'request_budget_3600', 'request_budget_86400',
               'request_budget_total', 'provider_backoff', 'daily_nothing_judged', 'daily_compose_failed',
               'timeout', 'transport_error', 'robots_timeout', 'robots_transport_error',
               'robots_disallowed', 'robots_disallowed_or_delayed', 'host_not_allowed',
               'asset_host_not_allowed', 'response_too_large', 'invalid_content_type',
               'invalid_csv', 'invalid_csv_shape', 'csv_rows_missing', 'invalid_search_payload',
               'invalid_search_offset', 'search_pagination_stalled', 'invalid_detail_payload',
               'detail_title_missing', 'attachment_body_missing', 'robots_delay_exceeds_budget',
               'robots_too_large', 'robots_redirect_limit', 'listing_no_article_links',
               'invalid_article_url', 'incomplete_article', 'detail_parse_or_fetch_failed',
               'detail_data_missing', 'detail_data_invalid', 'detail_alias_mismatch',
               'detail_body_invalid', 'invalid_feed', 'decode_error', 'invalid_listing_payload',
               'listing_pagination_stalled', 'all_details_failed', 'invalid_sitemap',
               'listing_links_missing', 'listing_records_missing'}
    return code if code in allowed else 'other'


def model_configuration(path=DEFAULT_MODEL_ENV, *, probe=False, client=None):
    try:
        base, key, model = load_local_credentials(path)
    except (OSError, ValueError):
        return {'configuration': 'invalid_or_missing', 'availability': 'not_probed'}
    report = {'configuration': 'valid', 'availability': 'not_probed'}
    if probe:
        if client is None:
            with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as local:
                return model_configuration(path, probe=True, client=local)
        try:
            response = client.get(base + '/models', headers={'Authorization': 'Bearer ' + key}, follow_redirects=False)
            if response.status_code != 200:
                report['availability'] = 'provider_unavailable'
            else:
                data = response.json().get('data')
                if not isinstance(data, list):
                    report['availability'] = 'invalid_models_response'
                else:
                    listed = any(isinstance(item, dict) and item.get('id') == model and
                                 (item.get('supported_endpoint_types') is None or
                                  'openai' in item.get('supported_endpoint_types', [])) for item in data)
                    report['availability'] = 'listed' if listed else 'model_not_listed'
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            report['availability'] = 'provider_unavailable'
    return report


def _safe_worker_configuration(marker):
    if not isinstance(marker, dict) or type(marker.get('collection')) is not bool:
        return None
    budget = marker.get('model_budget')
    if budget is not None and (not isinstance(budget, dict) or
                              any(type(budget.get(key)) is not int or budget[key] <= 0
                                  for key in ('minute', 'hour', 'day'))):
        return None
    return {'collection': marker['collection'],
            'model_budget': {key: budget[key] for key in ('minute', 'hour', 'day')} if budget else None,
            **_safe_identities(marker, WORKER_IDENTITY_FIELDS)}


def _safe_identities(marker, fields):
    return {key: marker[key] for key in fields
            if isinstance(marker.get(key), str) and re.fullmatch(r'[0-9a-f]{64}', marker[key])}


def worker_status(path, expected):
    if path is None or not path.is_file():
        return {'status': 'not_running'}
    try:
        with path.open('rb') as handle:
            handle.seek(1)
            marker = json.load(handle)
        # Existing file only; no touch/truncate. Windows locking needs a writable handle.
        with path.open('r+b') as handle:
            if os.name == 'nt':
                import msvcrt
                acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            try:
                acquire()
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    return {'status': 'unknown'}
                observed = _safe_worker_configuration(marker)
                return {'status': 'ready' if observed == expected else 'configuration_mismatch',
                        'observed_configuration': observed}
            else:
                release()
                return {'status': 'not_running'}
    except (OSError, ValueError):
        return {'status': 'unknown'}


def _coverage_entries(metrics):
    report = {}
    entries = metrics.get('entries')
    if not isinstance(entries, dict):
        return report
    for name, entry in entries.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name) or not isinstance(entry, dict):
            continue
        evidence = {}
        if entry.get('status') in {'complete', 'partial', 'failed'}:
            evidence['status'] = entry['status']
        reason = entry.get('reason')
        if isinstance(reason, str) and re.fullmatch(r'[a-z0-9_]+', reason):
            evidence['reason'] = reason
        for field in ('pages', 'undated'):
            if type(entry.get(field)) is int:
                evidence[field] = entry[field]
        for flag in ('reused', 'supplemental'):
            if entry.get(flag) is True:
                evidence[flag] = True
        for field in ('window_start', 'window_end', 'oldest_at', 'newest_at', 'available_from', 'from', 'through'):
            if isinstance(entry.get(field), str):
                try:
                    evidence[field] = _time(entry[field]).isoformat()
                except (ValueError, AttributeError):
                    pass
        report[name] = evidence
    return report


def _body_coverage(db, source, run, coverage):
    counts = {'complete': 0, 'pending': 0, 'unconfirmed': 0}
    if not run:
        return 'unknown', counts
    jobs = {}
    for row in db.execute("""
        SELECT json_extract(payload, '$.url') AS url, status,
               json_extract(result, '$.status') AS result_status,
               json_extract(result, '$.error') AS result_error
        FROM work_items
        WHERE kind='extract' AND json_extract(payload, '$.slug')=?
          AND json_extract(payload, '$.url') IN (SELECT url FROM discoveries WHERE run_id=?)
        ORDER BY json_extract(payload, '$.discovered_at') DESC, due_at DESC, id DESC
    """, (source['slug'], run['id'])):
        jobs.setdefault(row['url'], row)
    for row in db.execute("""
        SELECT DISTINCT discoveries.url, materials.collection_state,
               length(trim(materials.source_body)) > 0 AS has_body
        FROM discoveries LEFT JOIN materials
          ON materials.id = discoveries.material_id OR
             (discoveries.material_id IS NULL AND materials.canonical_url = discoveries.url)
        WHERE run_id=? AND outcome NOT IN ('outside_window', 'rejected', 'deferred')
    """, (run['id'],)):
        job = jobs.get(row['url'])
        if job and job['result_status'] == 'deferred':
            continue
        if (job and job['status'] in {'pending', 'running'}) or row['collection_state'] == 'pending':
            counts['pending'] += 1
        elif job and (job['status'] == 'failed' or job['result_error'] or job['result_status'] == 'unconfirmed'):
            counts['unconfirmed'] += 1
        elif row['has_body'] and row['collection_state'] != 'unconfirmed':
            counts['complete'] += 1
        else:
            counts['unconfirmed'] += 1
    if counts['pending'] or counts['unconfirmed']:
        return 'partial', counts
    return ('complete' if counts['complete'] or coverage == 'complete' else 'unknown'), counts


def database_snapshot(path, now):
    if path is None or not path.is_file():
        return {'status': 'unavailable', 'reason': 'existing_sqlite_database_required'}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            count = lambda query, args=(): db.execute(query, args).fetchone()[0]
            sources = []
            for source in db.execute('SELECT * FROM sources ORDER BY slug'):
                run = db.execute("""
                    SELECT * FROM source_runs WHERE source_id=?
                        AND COALESCE(json_extract(fetch_metrics, '$.mode'), '') NOT IN ('historical', 'bounded')
                    ORDER BY started_at DESC, id DESC LIMIT 1
                """, (source['id'],)).fetchone()
                due = _time(source['next_fetch_at'])
                tolerance = timedelta(minutes=max(15, source['interval_minutes'] or 60))
                started_at = _time(run['started_at']) if run else None
                age = max(0, int((now - started_at).total_seconds())) if started_at else None
                status = 'disabled' if not source['enabled'] else 'bootstrap' if not run else 'ok'
                if source['enabled'] and not run:
                    # Newly bootstrapped registries get a bounded first-fetch grace.
                    anchor = _time(source['collection_initialized_at']) or datetime.fromtimestamp(path.stat().st_mtime, UTC)
                    if due and now > due + tolerance or not due and now > anchor + max(tolerance, timedelta(minutes=30)):
                        status = 'stale'
                if source['enabled'] and run:
                    if run['status'] == 'failed':
                        status = 'failed'
                    elif due and now > due + tolerance:
                        status = 'stale'
                    elif run['status'] == 'running' and age is not None and age > max(1800, tolerance.total_seconds()):
                        status = 'stale'
                metrics = json.loads(run['fetch_metrics'] or '{}') if run else {}
                coverage = metrics.get('coverage')
                if coverage not in {'complete', 'partial'}:
                    coverage = 'legacy' if run and run['status'] != 'running' else 'unknown'
                body_coverage, bodies = _body_coverage(db, source, run, coverage)
                sources.append({'slug': source['slug'], 'status': status,
                                'latest_run_id': run['id'] if run else None,
                                'latest_run_at': started_at.isoformat() if started_at else None,
                                'latest_run_status': run['status'] if run else None, 'age_seconds': age,
                                'latest_error': provider_error(run['error_code']) if run and run['error_code'] else None,
                                'next_fetch_at': source['next_fetch_at'],
                                'new': metrics.get('added', 0), 'repeated': metrics.get('duplicates', 0),
                                'candidates': run['candidate_count'] if run else 0,
                                'coverage': coverage, 'coverage_entries': _coverage_entries(metrics),
                                'coverage_gaps': _coverage_entries({'entries': metrics.get('coverage_gaps')}),
                                'body_coverage': body_coverage, 'bodies': bodies,
                                **_safe_identities(metrics, IDENTITY_FIELDS),
                                'permissions': {name: bool(source[name]) for name in
                                                ('excerpt_allowed', 'full_text_allowed', 'media_allowed',
                                                 'syndicate_full_text_allowed')}})
            failures = Counter()
            for row in db.execute("SELECT error FROM work_items WHERE status='failed'"):
                failures[provider_error(row['error'])] += 1
            receipts = dict(db.execute('SELECT status,count(*) FROM paid_receipts GROUP BY status'))
            attempt_errors, response_status = Counter(), Counter()
            last_attempt, last_http_200, latest_failures = None, None, []
            for row in db.execute('SELECT sent_at,finished_at,error,response FROM paid_attempts ORDER BY sent_at DESC'):
                sent = _time(row['sent_at'])
                last_attempt = max(last_attempt, sent) if last_attempt else sent
                envelope = json.loads(row['response']) if row['response'] else {}
                status = envelope.get('status')
                if type(status) is int and 100 <= status <= 599:
                    response_status[str(status)] += 1
                    if status == 200:
                        completed = _time(row['finished_at']) or sent
                        last_http_200 = max(last_http_200, completed) if last_http_200 else completed
                code = provider_error(row['error'], row['response'])
                if code == 'other' and type(status) is int and status >= 400:
                    code = provider_error('provider_http_' + str(status))
                if code != 'other' or row['error']:
                    attempt_errors[code] += 1
                    if len(latest_failures) < 5:
                        latest_failures.append({'sent_at': sent.isoformat(), 'code': code})
            rolling = {}
            for name, seconds in (('minute', 60), ('hour', 3600), ('day', 86400)):
                rolling[name] = dict(db.execute('SELECT service,count(*) FROM paid_attempts WHERE sent_at>? GROUP BY service',
                                                ((now - timedelta(seconds=seconds)).replace(tzinfo=None).isoformat(' '),)))
            # Eligibility is delegated to the exact publication policy, in memory, with no ORM writes.
            from .models import Material, Source
            from .publication import translation_needed
            eligible = 0
            for row in db.execute('SELECT * FROM materials'):
                item = Material()
                for key in row.keys():
                    value = row[key]
                    if key.endswith('_at') or key == 'visible_after':
                        value = _time(value)
                    setattr(item, key, value)
                source_row = db.execute('SELECT * FROM sources WHERE id=?', (item.source_id,)).fetchone()
                if source_row is None:
                    continue
                item.source = Source(**dict(source_row))
                if translation_needed(item, at=now):
                    eligible += 1
            return {'status': 'ok', 'sources': sources,
                    'materials': {'total': count('SELECT count(*) FROM materials'),
                                  'new_last_day': count('SELECT count(*) FROM materials WHERE first_seen_at>?',
                                                       ((now - timedelta(days=1)).replace(tzinfo=None).isoformat(' '),)),
                                  'duplicates': count('SELECT count(*) FROM materials WHERE duplicate_of_id IS NOT NULL')},
                    'failed_jobs': dict(failures), 'paid_receipts': receipts,
                    'paid_attempt_errors': dict(attempt_errors), 'attempts_rolling_by_service': rolling,
                    'paid_response_status': dict(response_status),
                    'last_attempt_at': last_attempt.isoformat() if last_attempt else None,
                    'last_http_200_at': last_http_200.isoformat() if last_http_200 else None,
                    'latest_paid_failures': latest_failures,
                    'translation_eligible': eligible,
                    'model_settings': dict(db.execute('SELECT capability,model FROM admin_model_settings'))}
    except (sqlite3.Error, ValueError, TypeError, AttributeError):
        return {'status': 'unavailable', 'reason': 'snapshot_failed_or_schema_incompatible'}


def _http_ready(client, url, property_name, expected=None):
    try:
        response = client.get(url)
        body = response.json()
        return response.status_code == 200 and property_name in body and (expected is None or body[property_name] == expected)
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def audit(*, probe_model=False, check_services=True):
    now = datetime.now(UTC)
    address = database_url()
    path = sqlite_database_path(address)
    enabled = os.environ.get('BLUEPULSE_MODEL_CALLS_ENABLED') == '1'
    try:
        budget = {name.lower(): int(os.environ.get('BLUEPULSE_MODEL_BUDGET_' + name, ''))
                  for name in ('MINUTE', 'HOUR', 'DAY')} if enabled else None
        valid_budget = budget is None or all(value > 0 for value in budget.values())
    except ValueError:
        budget, valid_budget = None, False
    expected = worker_configuration(collection=os.environ.get('BLUEPULSE_COLLECT_ENABLED') == '1',
                                    model_budget=budget, database=address)
    worker = worker_status(path.with_suffix('.worker.lock') if path else None, expected)
    snapshot = database_snapshot(path, now)
    models = {'default': model_configuration(probe=probe_model)}
    try:
        from .editorial import preset_paths
        from .model_steps import environment_models
        paths, settings = preset_paths(), environment_models()
        models = {alias: model_configuration(file, probe=probe_model) for alias, file in paths.items()}
        if snapshot['status'] == 'ok':
            settings.update(snapshot.pop('model_settings', {}))
        aliases_valid = all(alias in paths for alias in settings.values())
    except (ValueError, TypeError):
        aliases_valid = False
    services = {'worker': worker['status'], 'api': 'not_checked', 'web': 'not_checked'}
    if check_services:
        api = os.environ.get('BLUEPULSE_API_URL', 'http://127.0.0.1:' + os.environ.get('BLUEPULSE_LOCAL_API_PORT', '8000'))
        web = os.environ.get('BLUEPULSE_SITE_ORIGIN', 'http://127.0.0.1:' + os.environ.get('BLUEPULSE_LOCAL_WEB_PORT', '3000'))
        with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
            services['api'] = 'ready' if _http_ready(client, api.rstrip('/') + '/api/v1/health/ready', 'status', 'ready') else 'unavailable'
            services['web'] = 'ready' if _http_ready(client, web.rstrip('/') + '/api/bluepulse/site/stats', 'sources') else 'unavailable'
    degraded = []
    if snapshot['status'] != 'ok':
        degraded.append('database_snapshot_unavailable')
    else:
        if any(source['status'] in {'failed', 'stale'} for source in snapshot['sources']):
            degraded.append('source_collection_failed_or_stale')
        active = [source for source in snapshot['sources'] if source['status'] != 'disabled']
        if any(source['coverage'] == 'partial' for source in active):
            degraded.append('source_coverage_partial')
        if any(source['body_coverage'] == 'partial' for source in active):
            degraded.append('source_body_incomplete')
        if snapshot['failed_jobs']:
            degraded.append('failed_jobs_recorded')
        if snapshot['paid_receipts'].get('unknown') or snapshot['paid_receipts'].get('pending'):
            degraded.append('unresolved_paid_receipts')
    if enabled and snapshot['status'] == 'ok' and budget:
        if any(count >= budget[window] for window, services_used in snapshot['attempts_rolling_by_service'].items()
               for count in services_used.values()):
            degraded.append('model_budget_wait')
    if enabled and (not valid_budget or not aliases_valid or any(m['configuration'] != 'valid' for m in models.values())):
        degraded.append('model_configuration_invalid')
    if probe_model and any(m['availability'] != 'listed' for m in models.values()):
        degraded.append('model_availability_not_verified')
    return {'checked_at': now.isoformat(), 'services': services,
            'services_ready': all(state == 'ready' for state in services.values()),
            'requested_worker_configuration': expected,
            'actual_worker_configuration': worker.get('observed_configuration'),
            'collection': ('enabled' if worker['observed_configuration']['collection'] else 'paused')
                          if worker.get('observed_configuration') else 'unknown',
            'model_calls': ('enabled' if worker['observed_configuration']['model_budget'] else 'paused')
                           if worker.get('observed_configuration') else 'unknown',
            'budget_limits': budget,
            'budget_valid': valid_budget, 'models': models, 'pipeline': snapshot,
            'degraded': degraded, 'note': 'Read-only snapshot; model listing is not generation verification.'}


def print_human(report):
    print('Pulse 内容流水线审计（只读）')
    print('服务：' + '；'.join(f'{name}={state}' for name, state in report['services'].items()))
    requested = report['requested_worker_configuration']
    print(f"本次请求配置：采集={'启用' if requested['collection'] else '暂停'}；模型={'启用' if requested['model_budget'] else '暂停'}")
    print(f"运行中 Worker：采集={report['collection']}；模型={report['model_calls']}（未知时不推断）")
    actual = report.get('actual_worker_configuration') or {}
    for key, title in (('collection_rule_version', '采集规则版本'),
                       ('collection_entry_fingerprint', '入口配置指纹'), ('database_fingerprint', '目标库指纹')):
        print(f"{title}：期望={requested.get(key) or '未知'}；运行中={actual.get(key) or '未知'}")
    for alias, model in report['models'].items():
        print(f"模型 {alias}：配置={model['configuration']}；提供方 /models={model['availability']}")
    pipeline = report['pipeline']
    if pipeline['status'] == 'ok':
        counts = Counter(source['status'] for source in pipeline['sources'])
        print('信源：' + '；'.join(f'{state} {count}' for state, count in sorted(counts.items())))
        for source in pipeline['sources']:
            if source['status'] in {'failed', 'stale'}:
                print(f"  {source['slug']}：{source['status']}；错误={source['latest_error'] or '-'}；距最近采集 {source['age_seconds']} 秒")
            if source['status'] != 'disabled':
                print(f"  {source['slug']}：列表覆盖={source['coverage']}；正文={source['body_coverage']} {source['bodies']}")
                for name, entry in source['coverage_entries'].items():
                    if entry.get('status') in {'partial', 'failed'}:
                        print(f"    {name}：{entry['status']}；{entry.get('reason') or '-'}；窗口 {entry.get('window_start') or '-'} 到 {entry.get('window_end') or '-'}")
                for name, gap in source['coverage_gaps'].items():
                    print(f"    {name}：待核验 {gap.get('from') or '-'} 到 {gap.get('through') or '-'}；{gap.get('reason') or '-'}")
        materials = pipeline['materials']
        print(f"材料：共 {materials['total']}；24小时新增 {materials['new_last_day']}；重复 {materials['duplicates']}；可翻译 {pipeline['translation_eligible']}")
        print(f"付费请求：响应状态={pipeline['paid_response_status']}；最近尝试={pipeline['last_attempt_at'] or '无'}")
        print(f"最近 HTTP 200={pipeline['last_http_200_at'] or '无'}（不代表业务处理成功）")
        print(f"失败任务={sum(pipeline['failed_jobs'].values())}；付费回执={pipeline['paid_receipts']}")
        for failure in pipeline['latest_paid_failures']:
            print(f"  最近付费失败：{failure['sent_at']} {failure['code']}")
    else:
        print('内容数据库：无法读取现有快照')
    print('降级项：' + ('；'.join(report['degraded']) or '未发现'))
    print('模型文件有效、/models 列出模型及 HTTP 200 均不等于生成业务已验证。')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--probe-model', action='store_true', help='GET /models only; no paid generation')
    args = parser.parse_args(argv)
    report = audit(probe_model=args.probe_model)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print_human(report)
    return 1 if not report['services_ready'] or report['degraded'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
