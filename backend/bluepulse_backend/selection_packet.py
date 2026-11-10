"""Private, reproducible real-material review packets; never writes the reading database.

Calibration methodology: AIHOT docs/selection.md (MIT, Copyright (c) 2026 数字生命卡兹克).
Only original material is exported. Model judgements never become human answers.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import random
import re
import sqlite3


# The review packet can keep an unclassified human answer without adding a public site category.
TOPICS = {'product', 'practice', 'paper', 'law', 'embodied', 'public-opinion', 'low-altitude', 'other'}
RELEVANCE = {'direct', 'potential', 'irrelevant', 'uncertain'}
DECISIONS = {'select', 'reject', 'uncertain'}
EVIDENCE = {'marketing', 'announcement', 'lab_test', 'pilot_observation', 'field_evaluation', 'unknown'}
ROOT = Path(__file__).resolve().parents[2]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def atomic_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def read_materials(path: Path) -> list[dict]:
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute('''
            SELECT m.id material_id, m.revision, m.content_hash, s.slug source_slug,
              s.name source_name, s.source_type, m.language, m.source_title title,
              m.source_url, coalesce(m.published_at,m.published_date) published_at,
              m.source_body body, m.body_status, s.tier, s.selection_threshold
            FROM materials m JOIN sources s ON s.id=m.source_id
            WHERE m.duplicate_of_id IS NULL AND m.withdrawn=0
              AND s.participation_mode='editorial' AND m.source_body IS NOT NULL
            ORDER BY m.id''') if len(''.join(row['body'].split())) >= 300]


def material_kind(row):
    text = (row['title'] + '\n' + row['body'][:2500]).lower()
    if re.search(r'采购|招标|procurement|tender|contract award', text):
        return 'procurement'
    if re.search(r'论文|研究报告|research|journal|study|evaluation', text):
        return 'research'
    if re.search(r'法规|标准|条例|regulation|legislation|standard|guidance', text):
        return 'policy'
    return 'practice-product-news'


def _balanced(rows, count, seed):
    buckets = defaultdict(list)
    for row in sorted(rows, key=lambda r: r['material_id']):
        buckets[(row['source_slug'], material_kind(row))].append(row)
    rng = random.Random(seed)
    keys = sorted(buckets)
    rng.shuffle(keys)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    result = []
    while len(result) < count:
        for key in keys:
            if buckets[key] and len(result) < count:
                result.append(buckets[key].pop())
        if not any(buckets.values()):
            break
    return result


def make_packet(rows, *, seed='pulse-policing-calibration-v1'):
    unique, titles, bodies = [], set(), set()
    for row in sorted(rows, key=lambda r: r['material_id']):
        title = re.sub(r'\W+', '', row['title']).casefold()
        body = digest(' '.join(row['body'].split()))
        if title in titles or body in bodies:
            continue
        titles.add(title)
        bodies.add(body)
        unique.append(row)
    if len(unique) < 120:
        raise ValueError('insufficient_real_materials')
    chinese = [r for r in unique if r['language'].lower().startswith('zh')]
    foreign = [r for r in unique if r not in chinese]
    zh_count = min(30, len(chinese))
    other_count = min(120 - zh_count, len(foreign))
    zh_count = 120 - other_count
    selected = _balanced(chinese, zh_count, seed + ':zh') + _balanced(foreign, other_count, seed + ':foreign')
    random.Random(seed + ':display').shuffle(selected)
    identity = digest([[r['material_id'], r['revision'], r['content_hash']] for r in selected])
    packet_id = 'pulse-review-' + identity[:16]
    cases = []
    private = {}
    for index, row in enumerate(selected, 1):
        case_id = f'P{index:03}'
        case = {k: row[k] for k in ('material_id','revision','content_hash','source_slug','source_name',
                                    'source_type','language','title','source_url','published_at','body')}
        case.update(case_id=case_id, body_status=row.get('body_status','full_text'),
                    analysis_text=row['body'][:12000], input_truncated=len(row['body']) > 12000,
                    assist={'title_zh': row['title'], 'body_zh': row['body'][:12000], 'status': 'original_zh'}
                    if row['language'].lower().startswith('zh') else None)
        cases.append(case)
        private[case_id] = {'tier': row['tier'], 'selection_threshold': row['selection_threshold'],
                            'kind': material_kind(row)}
    holdout = {r['material_id'] for r in _balanced(selected, 24, seed + ':holdout')}
    splits = {c['case_id']: 'holdout' if c['material_id'] in holdout else 'development' for c in cases}
    coverage = {'sources': dict(Counter(c['source_name'] for c in cases)),
                'languages': dict(Counter(c['language'] for c in cases)),
                'material_kinds': dict(Counter(material_kind(r) for r in selected)),
                'available_unique': len(unique), 'removed_exact_duplicates': len(rows) - len(unique),
                'notes': ['这是来源与材料类型的分层抽样，不是人工确认的正负例配比。',
                          '上游模型发布、机器人、无人机和高价值正例的覆盖，仍须负责人标注后核对；不足时另补真实材料。',
                          '先按单篇内容本身判断价值，不因旧稿、转载或另一篇已被选过而直接判不精选。',
                          '英文辅助译文由模型独立翻译，可能有误；原文是证据。']}
    now = datetime.now(UTC).isoformat()
    data = {'schema_version': 1, 'packet_id': packet_id, 'created_at': now, 'cases': cases, 'coverage': coverage}
    manifest = {'schema_version': 1, 'packet_id': packet_id, 'seed': seed, 'created_at': now,
                'splits': splits, 'source_settings': private,
                'case_fingerprints': {c['case_id']:digest({k:v for k,v in c.items() if k != 'assist'}) for c in cases},
                'bindings': {c['case_id']: {k:c[k] for k in ('material_id','revision','content_hash')} for c in cases}}
    return data, manifest


def render_html(data):
    import base64
    assets = Path(__file__).with_name('review_assets')
    template = (assets / 'review.html').read_text(encoding='utf-8')
    encoded = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    encoded = encoded.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    font = base64.b64encode((ROOT / 'src/app/fonts/GoogleSans-Variable.woff2').read_bytes()).decode()
    # Replace data last: article text may itself contain a template token.
    return (template.replace('%%STYLE%%', (assets/'review.css').read_text(encoding='utf-8'))
            .replace('%%SCRIPT%%', (assets/'review.js').read_text(encoding='utf-8'))
            .replace('%%FONT%%', font).replace('%%PACKET%%', encoded))


def validate_gold(gold, *, confirmed=True):
    if not isinstance(gold, dict):
        raise ValueError('invalid_gold')
    if not confirmed:
        return
    if (gold.get('relevance') not in RELEVANCE or gold.get('select') not in DECISIONS or
            gold.get('evidence_level') not in EVIDENCE or
            not isinstance(gold.get('reason'), str) or not 1 <= len(gold['reason'].strip()) <= 3000 or
            gold.get('primary_topic') is not None and gold['primary_topic'] not in TOPICS):
        raise ValueError('invalid_gold')
    if gold['relevance'] in {'direct','potential'} and gold.get('primary_topic') not in TOPICS:
        raise ValueError('related_requires_topic')
    if gold['relevance'] == 'irrelevant' and gold['select'] != 'reject':
        raise ValueError('irrelevant_must_reject')


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise ValueError('invalid_timestamp')
    try:
        if value[-1] != 'Z' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
            raise ValueError('invalid_offset')
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if at.tzinfo is None:
            raise ValueError('timezone_required')
        at = at.astimezone(UTC)
        return at.replace(microsecond=at.microsecond // 1000 * 1000)
    except (ValueError, OverflowError) as exc:
        raise ValueError('invalid_timestamp') from exc


def validate_bundle(data, bundle):
    if not isinstance(bundle, dict) or bundle.get('schema_version') != 1 or bundle.get('packet_id') != data['packet_id']:
        raise ValueError('packet_binding_mismatch')
    cases = {c['case_id']:c for c in data['cases']}
    ids = {}
    for key in ('records','drafts','resolutions'):
        if not isinstance(bundle.get(key), list) or len(bundle[key]) > 20000:
            raise ValueError('invalid_review_list')
        for row in bundle[key]:
            if not isinstance(row, dict) or row.get('case_id') not in cases:
                raise ValueError('case_binding_mismatch')
            case = cases[row['case_id']]
            if not isinstance(row.get('reviewer'), str) or not 1 <= len(row['reviewer'].strip()) <= 80:
                raise ValueError('invalid_reviewer')
            _timestamp(row.get('updated_at'))
            if key == 'resolutions':
                if (not isinstance(row.get('reason'), str) or not 1 <= len(row['reason'].strip()) <= 3000 or
                        not isinstance(row.get('record_ids'), list) or not row['record_ids'] or
                        any(not isinstance(i,str) for i in row['record_ids']) or
                        len(set(row['record_ids'])) != len(row['record_ids']) or
                        row.get('chosen_record_id') not in row['record_ids']):
                    raise ValueError('invalid_resolution')
                id = row.get('resolution_id')
            else:
                if row.get('revision') != case['revision'] or row.get('content_hash') != case['content_hash']:
                    raise ValueError('material_binding_mismatch')
                if key == 'records' and row.get('confirmed') is not True:
                    raise ValueError('unconfirmed_record')
                validate_gold(row.get('gold'), confirmed=key == 'records')
                id = row.get('record_id') if key == 'records' else None
            if key != 'drafts':
                if not isinstance(id,str) or not 1 <= len(id) <= 160:
                    raise ValueError('invalid_record_id')
                binding = (key, id)
                if binding in ids and ids[binding] != digest(row):
                    raise ValueError('immutable_record_conflict')
                ids[binding] = digest(row)
    record_index = {r['record_id']:r for r in bundle['records']}
    for row in bundle['resolutions']:
        if any(id not in record_index or record_index[id]['case_id'] != row['case_id'] for id in row['record_ids']):
            raise ValueError('resolution_binding_mismatch')


def consensus(data, bundle):
    validate_bundle(data, bundle)
    result = {}
    for case in data['cases']:
        votes = {}
        for record in bundle['records']:
            if record['case_id'] == case['case_id']:
                # Ties are retained, not broken arbitrarily by import order.
                previous = votes.get(record['reviewer'], [])
                if not previous or _timestamp(record['updated_at']) > _timestamp(previous[0]['updated_at']):
                    votes[record['reviewer']] = [record]
                elif _timestamp(record['updated_at']) == _timestamp(previous[0]['updated_at']):
                    if all(r['record_id'] != record['record_id'] for r in previous):
                        previous.append(record)
        active = [r for group in votes.values() for r in group]
        # Rationale disagreements are retained too: the reason is part of the human standard.
        decisions = {digest(r['gold']) for r in active}
        current_ids = sorted(r['record_id'] for r in active)
        resolutions = [r for r in bundle['resolutions'] if r['case_id'] == case['case_id'] and
                       sorted(r['record_ids']) == current_ids]
        status, gold = ('pending', None) if not active else ('confirmed', active[0]['gold'])
        if len(decisions) > 1:
            status, gold = 'conflict', None
            if resolutions:
                latest = max(_timestamp(r['updated_at']) for r in resolutions)
                final = [r for r in resolutions if _timestamp(r['updated_at']) == latest]
                choices = {r['chosen_record_id'] for r in final}
                if len(choices) == 1:
                    gold = next(r['gold'] for r in active if r['record_id'] == next(iter(choices)))
                    status = 'resolved'
        result[case['case_id']] = {'status':status, 'gold':gold, 'record_ids':current_ids}
    return result


def load_packet(directory):
    data = json.loads((directory/'packet.json').read_text(encoding='utf-8'))
    manifest = json.loads((directory/'manifest.private.json').read_text(encoding='utf-8'))
    if data['packet_id'] != manifest['packet_id']:
        raise ValueError('manifest_binding_mismatch')
    ids = [case['case_id'] for case in data['cases']]
    if len(ids) != 120 or len(set(ids)) != 120 or set(ids) != set(manifest['splits']):
        raise ValueError('manifest_case_mismatch')
    holdout = {r['material_id'] for r in _balanced(data['cases'],24,manifest['seed'] + ':holdout')}
    expected = {c['case_id']: 'holdout' if c['material_id'] in holdout else 'development' for c in data['cases']}
    if manifest['splits'] != expected:
        raise ValueError('manifest_split_mismatch')
    for case in data['cases']:
        binding = {k:case[k] for k in ('material_id','revision','content_hash')}
        if binding != manifest['bindings'].get(case['case_id']):
            raise ValueError('manifest_material_mismatch')
        if digest({k:v for k,v in case.items() if k != 'assist'}) != manifest['case_fingerprints'].get(case['case_id']):
            raise ValueError('frozen_material_changed')
    return data, manifest


def read_reviews(path):
    """Accept portable returned HTML or JSON without executing or loading any HTML resources."""
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('review_file_too_large')
    raw = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() not in {'.html','.htm'}:
        return json.loads(raw)
    class EmbeddedReview(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.capture = False
            self.parts = []
            self.matches = 0
        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == 'script' and attributes.get('id') == 'embedded-review':
                if attributes.get('type') != 'application/json':
                    raise ValueError('review_script_type_invalid')
                self.matches += 1
                self.capture = True
        def handle_endtag(self, tag):
            if tag == 'script':
                self.capture = False
        def handle_data(self, text):
            if self.capture:
                self.parts.append(text)
    parsed = EmbeddedReview()
    parsed.feed(raw)
    if parsed.matches != 1:
        raise ValueError('annotated_html_required')
    return json.loads(''.join(parsed.parts))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--database', type=Path, default=ROOT/'backend/data/bluepulse.db')
    prepare.add_argument('--output-dir', type=Path, required=True)
    render = sub.add_parser('render')
    render.add_argument('--packet-dir', type=Path, required=True)
    gold = sub.add_parser('gold')
    gold.add_argument('--packet-dir', type=Path, required=True)
    gold.add_argument('--reviews', type=Path, required=True)
    gold.add_argument('--output', type=Path, required=True)
    gold.add_argument('--split', choices=['development','holdout'], default='development')
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            parser.error('output directory must be empty; render/translate can resume existing packets')
        data, manifest = make_packet(read_materials(args.database))
        args.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output_dir/'packet.json', data)
        atomic_json(args.output_dir/'manifest.private.json', manifest)
        (args.output_dir/'Pulse选稿标注.html').write_text(render_html(data), encoding='utf-8')
        print(json.dumps({'packet_id':data['packet_id'], 'cases':120, 'development':96, 'holdout':24,
                          'coverage':data['coverage']}, ensure_ascii=False))
    elif args.command == 'render':
        data, _ = load_packet(args.packet_dir)
        (args.packet_dir/'Pulse选稿标注.html').write_text(render_html(data),encoding='utf-8')
    else:
        data, manifest = load_packet(args.packet_dir)
        bundle = read_reviews(args.reviews)
        decisions = consensus(data,bundle)
        missing = [case_id for case_id,row in decisions.items() if manifest['splits'][case_id] == args.split and
                   row['status'] not in {'confirmed','resolved'}]
        if missing:
            parser.error(f'{args.split}: {len(missing)} pending/conflicting cases; no gold file written')
        rows = [dict(case, split=args.split, gold=decisions[case['case_id']]['gold']) for case in data['cases']
                if manifest['splits'][case['case_id']] == args.split]
        # Opening with x prevents an accidental overwrite of the chosen frozen gold version.
        with args.output.open('x',encoding='utf-8') as output:
            for row in rows:
                output.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps({'split':args.split,'confirmed':len(rows),'output':str(args.output)},ensure_ascii=False))


if __name__ == '__main__':
    main()
