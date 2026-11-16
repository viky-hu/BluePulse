"""Opt-in independent candidate-quality evaluation against completed human reviews.

Only the production relevance decision and two scoring rounds run. Category,
writing, grouping and final publication are outside this evaluation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sqlite3

import httpx
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from . import editorial
from .db import Base, database_url, make_engine
from .editorial import preset_paths
from .editorial_models import PaidAttempt, PaidReceipt
from .live_model import SCORE_PROMPT, load_local_credentials
from .model_steps import Steps, environment_models
from .receipts import Budget, BudgetWait, ReceiptUnknown
from .runtime_health import provider_error
from .selection_packet import atomic_json, consensus, digest, load_packet, read_reviews
from .selection_scoring import WEIGHTS


def chosen_gold(directory, reviews, split, confirm_holdout, *, confirmed_only=False):
    if split not in {'development', 'holdout'}:
        raise ValueError('invalid_split')
    if split == 'holdout' and not confirm_holdout:
        raise ValueError('holdout_confirmation_required')
    data, manifest = load_packet(directory)
    bundle = read_reviews(reviews)
    decisions = consensus(data, bundle)
    selected = [case for case in data['cases'] if manifest['splits'][case['case_id']] == split]
    if confirmed_only:
        selected = [case for case in selected if decisions[case['case_id']]['status'] != 'pending']
    if not selected or any(decisions[case['case_id']]['status'] not in {'confirmed', 'resolved'} for case in selected):
        raise ValueError('incomplete_or_conflicting_gold')
    return data, manifest, selected, {case['case_id']:decisions[case['case_id']] for case in selected}


def evaluate_case(case, step, threshold, *, previous=None, save=lambda state: None):
    state = previous if previous is not None else {'status':'running', 'scores':[], 'request_ids':[]}
    if state['status'] in {'scored', 'blocked', 'unscored', 'failed', 'unknown'}:
        return state
    text = (case.get('body') or '')[:12000]
    if 'prefilter' not in state:
        decision = editorial.run_prefilter(
            step, {'title':case['title'], 'text':text, 'bodyStatus':case.get('body_status','full_text')})
        state.update(prefilter=decision['label'], relevance_decision=decision)
        save(state)
    if state['prefilter'] == 'BLOCK':
        state.update(status='blocked', prediction=False)
    elif state['prefilter'] == 'UNKNOWN' or not text.strip():
        state.update(status='unscored', prediction=None)
    else:
        for ordinal in range(len(state['scores']) + 1, 3):
            score, request_id, content_type = editorial._score(step, {'title':case['title'], 'text':text}, ordinal)
            if request_id and request_id in state['request_ids']:
                raise ValueError('duplicate_score_response')
            state['scores'].append(score)
            state['request_ids'].append(request_id)
            state.setdefault('content_types', []).append(content_type)
            save(state)
        state.update(status='scored', score=sum(state['scores']) // 2,
                     prediction=sum(state['scores']) >= 2 * threshold if threshold is not None else None)
    save(state)
    return state


def metrics(rows):
    certain = [row for row in rows if row['gold']['select'] in {'select','reject'}]
    known = [row for row in certain if type(row.get('prediction')) is bool and row.get('status') in {'scored','blocked'}]
    positive = sum(row['gold']['select'] == 'select' for row in certain)
    tp = sum(row['prediction'] is True and row['gold']['select'] == 'select' for row in known)
    fp = sum(row['prediction'] is True and row['gold']['select'] == 'reject' for row in known)
    fn = sum(row['prediction'] is False and row['gold']['select'] == 'select' for row in known)
    tn = sum(row['prediction'] is False and row['gold']['select'] == 'reject' for row in known)
    ratio = lambda numerator, denominator: numerator / denominator if denominator else None
    states = Counter(row.get('status') for row in rows)
    return {'total':len(rows), 'gold_certain':len(certain), 'gold_positive':positive,
            'gold_uncertain':len(rows)-len(certain), 'classified':len(known),
            'true_positive':tp, 'false_positive':fp, 'false_negative_classified':fn, 'true_negative':tn,
            'unclassified_gold_positive':positive-tp-fn, 'precision':ratio(tp,tp+fp),
            'recall':ratio(tp,positive), 'recall_classified':ratio(tp,tp+fn),
            'coverage':ratio(len(known),len(certain)), 'failed':states['failed'],
            'unknown':states['unknown'], 'unscored':states['unscored'],
            'uncalibrated':sum(row.get('status') == 'scored' and row.get('prediction') is None for row in rows),
            'prefilter':dict(Counter(row.get('prefilter','not_completed') for row in rows)),
            'can_calibrate':bool(positive and len(certain)-positive),
            'metric_policy':'Recall includes all gold positives; precision uses known predictions; uncertain gold excluded.'}


def prefilter_metrics(rows):
    decisions = []
    for row in rows:
        relevance = row['gold'].get('relevance','uncertain')
        label = row.get('prefilter')
        completed = label in {'PASS','BLOCK'}
        decisions.append({'gold':{'select':'select' if relevance in {'direct','potential'} else
                              'reject' if relevance == 'irrelevant' else 'uncertain'},
                      'prediction':label == 'PASS' if completed else None,
                      'status':'scored' if completed else 'unscored' if label == 'UNKNOWN' else row.get('status','unscored'),
                      'prefilter':label or 'not_completed'})
    result = metrics(decisions)
    result.update(scope='publication_relevance_gate', undecided=sum(row.get('prefilter') == 'UNKNOWN' for row in rows),
                  advancement_policy='PASS advances to publication checks; BLOCK and UNKNOWN stay private.')
    return result


def summarize(rows, *, scan):
    result = metrics(rows)
    result['relevance_gate'] = prefilter_metrics(rows)
    strata = {}
    for name in ('language', 'source_slug', 'gold_topic'):
        groups = defaultdict(list)
        for row in rows:
            groups[str(row['gold'].get('primary_topic') or 'none') if name == 'gold_topic' else row[name]].append(row)
        strata[name] = {key:metrics(group) for key, group in sorted(groups.items())}
    result['strata'] = strata
    if scan:
        result['threshold_scan'] = {}
        for threshold in range(40,91,2):
            adjusted = [dict(row, prediction=(sum(row['scores']) >= 2*threshold)
                             if row['status'] == 'scored' else row.get('prediction')) for row in rows]
            result['threshold_scan'][str(threshold)] = metrics(adjusted)
    else:
        result['threshold_scan'] = None
    return result


def _production_model_settings():
    settings = environment_models()
    url = make_url(database_url())
    if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
        raise ValueError('production_sqlite_settings_required')
    path = Path(url.database).resolve()
    if not path.is_file():
        raise ValueError('existing_production_settings_database_required')
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
            db.execute('PRAGMA query_only=ON')
            settings.update(dict(db.execute('SELECT capability,model FROM admin_model_settings')))
    except sqlite3.Error as exc:
        raise ValueError('production_model_settings_unavailable') from exc
    return {capability:settings.get(capability,'default') for capability in ('prefilter','score')}, path


def _safe_error(exc):
    value = getattr(exc,'code',None)
    if value is None and isinstance(exc,(ValueError,BudgetWait)):
        value = str(exc)
    if value in {'invalid_prefilter','duplicate_score_response','invalid_selection_score',
                 'model_configuration_changed','invalid_model_output', 'invalid_split',
                 'holdout_confirmation_required', 'incomplete_or_conflicting_gold',
                 'explicit_paid_model_opt_in_required', 'invalid_max_model_calls',
                 'production_sqlite_settings_required', 'existing_production_settings_database_required',
                 'production_model_settings_unavailable', 'model_alias_unavailable',
                 'evaluation_output_must_be_separate_from_packet', 'evaluation_output_must_be_isolated',
                 'evaluation_output_symlink_not_allowed', 'evaluation_resume_manifest_mismatch',
                 'evaluation_receipts_not_isolated', 'invalid_model_configuration'}:
        return value
    if isinstance(exc, ReceiptUnknown):
        return 'receipt_unknown'
    return provider_error(value)


def _usage(engine):
    fields = ('prompt_tokens','completion_tokens','total_tokens')
    def empty():
        return {'attempts':0,'statuses':{},'duration_ms':0,'duration_reported_attempts':0,
                'usage_reported_attempts':0,**dict.fromkeys(fields,0)}
    def account(target, status, envelope, usage):
        target['attempts'] += 1
        target['statuses'][status] = target['statuses'].get(status,0) + 1
        duration = envelope.get('duration_ms')
        if type(duration) in {int,float} and math.isfinite(duration) and duration >= 0:
            target['duration_ms'] += duration
            target['duration_reported_attempts'] += 1
        # OpenAI token fields only: input/output aliases never inflate the same usage.
        observed = False
        for field in fields:
            value = usage.get(field)
            if type(value) is int and value >= 0:
                target[field] += value
                observed = True
        target['usage_reported_attempts'] += int(observed)
    with Session(engine) as session:
        totals = [{'service':service, 'status':status, 'attempts':count} for service,status,count in
                  session.execute(select(PaidAttempt.service,PaidAttempt.status,func.count()).group_by(PaidAttempt.service,PaidAttempt.status))]
        per_model, overall = {}, empty()
        for status, response, request in session.execute(select(PaidAttempt.status,PaidAttempt.response,PaidReceipt.request).join(
                PaidReceipt,PaidReceipt.key == PaidAttempt.receipt_key)):
            model = (request.get('parameters') or {}).get('model','unknown')
            envelope = response if isinstance(response,dict) else {}
            try:
                body = envelope.get('body',{})
                body = json.loads(body) if isinstance(body,str) else body
            except (ValueError,TypeError):
                body = {}
            usage = body.get('usage',{}) if isinstance(body,dict) else {}
            usage = usage if isinstance(usage,dict) else {}
            account(overall,status,envelope,usage)
            account(per_model.setdefault(model,empty()),status,envelope,usage)
        return {'attempts_total':overall.pop('attempts'), **overall, 'by_model':per_model,
                'by_service_status':totals,
                'receipts':dict(session.execute(select(PaidReceipt.status,func.count()).group_by(PaidReceipt.status)).all()),
                'usage_policy':'Reported OpenAI fields only; missing usage/duration is unreported, not evidence of zero cost.'}


def run(directory, reviews, output, *, split='development', confirm_holdout=False, confirmed_only=False,
        allow_paid=False, max_calls=360):
    # Validation and selected-split consensus happen before credentials, network, mkdir or DB creation.
    data, packet_manifest, cases, decisions = chosen_gold(
        directory, reviews, split, confirm_holdout, confirmed_only=confirmed_only)
    if not allow_paid:
        raise ValueError('explicit_paid_model_opt_in_required')
    if type(max_calls) is not int or not 1 <= max_calls <= 10000:
        raise ValueError('invalid_max_model_calls')
    settings, production_path = _production_model_settings()
    presets = preset_paths()
    aliases = sorted(set(settings.values()))
    if any(alias not in presets for alias in aliases):
        raise ValueError('model_alias_unavailable')
    credentials = {alias:load_local_credentials(presets[alias]) for alias in aliases}
    pins = {alias:editorial.input_hash(json.dumps([base,model])) for alias,(base,key,model) in credentials.items()}
    if output.is_symlink():
        raise ValueError('evaluation_output_symlink_not_allowed')
    output = output.resolve()
    if output == directory.resolve() or directory.resolve() in output.parents:
        raise ValueError('evaluation_output_must_be_separate_from_packet')
    if production_path == output/'receipts.sqlite3' or production_path in output.parents or output == production_path.parent:
        raise ValueError('evaluation_output_must_be_isolated')
    if output.is_symlink() or output.exists() and any(child.is_symlink() for child in output.iterdir()):
        raise ValueError('evaluation_output_symlink_not_allowed')
    frozen = {'schema_version':1, 'packet_id':data['packet_id'], 'split':split, 'confirmed_only':confirmed_only,
              'case_fingerprints':{case['case_id']:digest({key:value for key,value in case.items() if key != 'assist'}) for case in cases},
              'gold_hash':digest(decisions), 'settings':settings, 'model_pins':pins,
              'prompt_hash':digest([editorial.PREFILTER,SCORE_PROMPT,WEIGHTS]),
              'evaluation_policy':{'revision':2,'input_chars':12000,'prefilter_tokens':600,'score_tokens':512,'rounds':2},
              'source_settings':{case['case_id']:packet_manifest['source_settings'][case['case_id']] for case in cases},
              'max_model_calls':max_calls}
    manifest_path = output/'evaluation.manifest.json'
    if output.exists() and any(output.iterdir()):
        if not manifest_path.is_file() or json.loads(manifest_path.read_text(encoding='utf-8')) != frozen:
            raise ValueError('evaluation_resume_manifest_mismatch')
    else:
        output.mkdir(parents=True,exist_ok=True)
        atomic_json(manifest_path,frozen)
    database = output/'receipts.sqlite3'
    if database.exists() and (database.is_symlink() or database.stat().st_nlink != 1):
        raise ValueError('evaluation_receipts_not_isolated')
    engine = make_engine('sqlite:///'+database.as_posix())
    # Only receipt tables belong in the isolated evaluation store.
    Base.metadata.create_all(engine,tables=[PaidReceipt.__table__,PaidAttempt.__table__])
    progress_path = output/'progress.json'
    progress = json.loads(progress_path.read_text(encoding='utf-8')) if progress_path.is_file() else {}
    budget = Budget(max_calls,max_calls,max_calls,total=max_calls)
    run_key = 'selection-evaluation:'+digest(frozen)
    try:
        with httpx.Client(timeout=httpx.Timeout(60,connect=10),follow_redirects=False,trust_env=False) as client:
            for case in cases:
                case_id = case['case_id']
                state = progress.setdefault(case_id,{'status':'running','scores':[],'request_ids':[]})
                def save(value):
                    progress[case_id] = value
                    atomic_json(progress_path,progress)
                step = Steps(engine,client,presets,settings,'evaluation:'+data['packet_id']+':'+case_id,
                             budget,run_key,pins=pins)
                try:
                    evaluate_case(case,step,frozen['source_settings'][case_id]['selection_threshold'],previous=state,save=save)
                except Exception as exc:
                    state.update(status='unknown' if isinstance(exc,ReceiptUnknown) else 'failed',
                                 error=_safe_error(exc),prediction=None)
                    save(state)
        rows = [dict(progress[case['case_id']],case_id=case['case_id'],language=case['language'],
                     source_slug=case['source_slug'],gold=decisions[case['case_id']]['gold'],
                     threshold=frozen['source_settings'][case['case_id']]['selection_threshold']) for case in cases]
        label = 'production-config-'+digest(settings)[:10]
        report = {'schema_version':1, 'packet_id':data['packet_id'], 'split':split,
                  'created_at':datetime.now(UTC).isoformat(), 'evaluation_scope':'selection_candidate_before_category_and_grouping',
                  'public_relevance_evaluated':True, 'production_database_written':False,
                  'models':{label:{'summary':summarize(rows,scan=split == 'development'), 'cases':rows,
                                   'usage':_usage(engine), 'capability_aliases':settings}},
                  'notes':['No structure, writing, grouping or publication stages executed.',
                           'Relevance results measure the first editorial gate before other publication checks.',
                           'Undefined metrics are null; calibration requires positive and negative human labels.']}
        atomic_json(output/'evaluation-report.json',report)
        return report
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-dir',type=Path,required=True)
    parser.add_argument('--reviews',type=Path,required=True,help='Exported JSON or returned annotated HTML')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--split',choices=['development','holdout'],default='development')
    parser.add_argument('--confirm-holdout',action='store_true')
    parser.add_argument('--confirmed-only',action='store_true',help='skip unmarked cases in the chosen split')
    parser.add_argument('--allow-paid-model',action='store_true')
    parser.add_argument('--max-model-calls',type=int,default=360)
    args = parser.parse_args(argv)
    try:
        report = run(args.packet_dir,args.reviews,args.output_dir,split=args.split,confirm_holdout=args.confirm_holdout,
                     confirmed_only=args.confirmed_only, allow_paid=args.allow_paid_model,max_calls=args.max_model_calls)
    except (ValueError,OSError) as exc:
        parser.error(_safe_error(exc))
    print(json.dumps(report,ensure_ascii=True))
    rows = next(iter(report['models'].values()))['cases']
    return 1 if any(row['status'] in {'failed','unknown'} or
                    row['status'] == 'unscored' and row.get('prefilter') != 'UNKNOWN' for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
