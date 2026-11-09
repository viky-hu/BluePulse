"""Independent Chinese reading aids, isolated receipts, bounded paid calls, resumable packets."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import argparse
import json
from pathlib import Path

import httpx

from .db import Base, make_engine
from .editorial import TRANSLATE, preset_paths, translate
from .live_model import load_local_credentials, model_listed
from .model_steps import Steps
from .receipts import Budget, BudgetWait
from .selection_packet import atomic_json, digest, load_packet, render_html


def translate_case(case, step):
    if (case.get('assist') or {}).get('status') in {'translated', 'original_zh'}:
        return case['assist']
    if case['language'].lower().startswith('zh'):
        return {'status':'original_zh', 'title_zh':case['title'], 'body_zh':case['analysis_text']}
    # Blank paragraph separators otherwise cause one paid call per paragraph. Single newlines
    # retain paragraph boundaries and are shielded by the existing production translator.
    text = case['title'] + '\n' + case['analysis_text'].replace('\r\n','\n')
    text = '\n'.join(line for line in text.split('\n') if line.strip())
    translated, complete = translate(text, step)
    if not complete or '\n' not in translated:
        raise ValueError('incomplete_review_translation')
    title, body = translated.split('\n', 1)
    return {'status':'translated', 'title_zh':title.strip(), 'body_zh':body.strip(),
            'input_hash':digest(text), 'prompt_hash':digest(TRANSLATE),
            'generated_at':datetime.now(UTC).isoformat(),
            'notice':'独立机器辅助译文，未经人工确认；判断以原文为准。'}


def run(directory, *, max_calls=800, concurrency=3):
    data, _ = load_packet(directory)
    presets = preset_paths()
    base, key, model = load_local_credentials(presets['default'])
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        if not model_listed(client,base,key,model):
            raise ValueError('review_model_not_listed')
    # A separate database holds paid response receipts only. Never projects public articles.
    engine = make_engine('sqlite:///' + (directory/'translation-receipts.sqlite3').resolve().as_posix())
    Base.metadata.create_all(engine)
    budget = Budget(60, max_calls, max_calls, total=max_calls)
    run_key = data['packet_id'] + ':reading-aid-v1'
    def one(case):
        if case['language'].startswith('zh') or (case.get('assist') or {}).get('status') == 'translated':
            return translate_case(case,None)
        with httpx.Client(timeout=httpx.Timeout(60,connect=15), follow_redirects=False) as client:
            # Steps uses editorial.input_hash(json.dumps(...)), preserve that exact identity.
            from .editorial import input_hash
            step = Steps(engine,client,presets,{},'review:'+data['packet_id']+':'+case['case_id'],budget,run_key,
                         pins={'default':input_hash(json.dumps([base,model]))})
            result = translate_case(case,step)
            result['model'] = model
            return result
    counts, failures = {}, []
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(one,case):case for case in data['cases']}
            for future in as_completed(futures):
                case = futures[future]
                try:
                    case['assist'] = future.result()
                except Exception as exc:
                    # Received refusals remain cached. Unknown outcomes are never auto-released here.
                    code = getattr(exc,'code',None) or (str(exc) if isinstance(exc,(BudgetWait,ValueError)) else type(exc).__name__)
                    failures.append({'case_id':case['case_id'],'code':code})
                    case['assist'] = {'status':'unavailable','title_zh':'','body_zh':'', 'error':code,
                                      'notice':'辅助译文未完成，请阅读原文或交由能阅读原文的组员复核。'}
                atomic_json(directory/'packet.json',data)
                completed = sum((c.get('assist') or {}).get('status') in {'translated','original_zh'} for c in data['cases'])
                print(json.dumps({'case_id':case['case_id'],'ready':completed,'total':len(data['cases']),
                                  'status':case['assist']['status']},ensure_ascii=True),flush=True)
        counts = {state:sum((c.get('assist') or {}).get('status') == state for c in data['cases'])
                  for state in ('translated','original_zh','unavailable')}
        report = {'packet_id':data['packet_id'],'model':model,'counts':counts,'failures':failures,
                  'max_requests_total':max_calls, 'production_database_written':False}
        atomic_json(directory/'translation-report.json',report)
        (directory/'Pulse选稿标注.html').write_text(render_html(data),encoding='utf-8')
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-dir',type=Path,required=True)
    parser.add_argument('--allow-paid-model',action='store_true')
    parser.add_argument('--max-model-calls',type=int,default=800)
    args = parser.parse_args()
    if not args.allow_paid_model:
        parser.error('independent translation requires --allow-paid-model; packet preparation is free')
    if not 1 <= args.max_model_calls <= 1000:
        parser.error('--max-model-calls must be 1..1000')
    report = run(args.packet_dir,max_calls=args.max_model_calls)
    print(json.dumps(report,ensure_ascii=True))
    if report['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
