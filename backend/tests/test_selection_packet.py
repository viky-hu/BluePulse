import json
import sqlite3

import pytest

from bluepulse_backend import selection_packet as packet


@pytest.mark.parametrize('relevance',['direct','potential'])
def test_annotation_other_category_is_valid_for_related_news(relevance):
    packet.validate_gold({'relevance':relevance,'select':'reject','primary_topic':'other',
                          'evidence_level':'unknown','reason':'有技术线索，但现有分类不贴切。'})


def test_sampling_is_frozen_balanced_and_blind():
    rows = [dict(material_id=str(i), revision=1, content_hash=f'h{i}', source_slug=f's{i % 8}',
                 source_name='真实来源', source_type='rss', language='zh' if i < 45 else 'en',
                 title=f'独立科技新闻 {i}', source_url=f'https://example.test/{i}',
                 body=f'Unique original evidence {i}. ' * 30, published_at=None,
                 tier='T1', selection_threshold=60) for i in range(260)]
    first, manifest = packet.make_packet(rows)
    second, repeated = packet.make_packet(list(reversed(rows)))
    assert first['packet_id'] == second['packet_id']
    assert [c['case_id'] for c in first['cases']] == [c['case_id'] for c in second['cases']]
    assert len(first['cases']) == 120
    assert sum(c['language'] == 'zh' for c in first['cases']) == 30
    assert list(manifest['splits'].values()).count('holdout') == 24
    assert list(manifest['splits'].values()).count('development') == 96
    assert manifest['splits'] == repeated['splits']
    for case in first['cases']:
        assert not {'tier', 'selection_threshold', 'scores', 'topics', 'split'} & case.keys()


def test_duplicates_and_insufficient_corpus_are_not_fabricated():
    row = dict(material_id='1', revision=1, content_hash='same', source_slug='s', source_name='s',
               source_type='rss', language='zh', title='同一篇原文', source_url='https://example.test/1',
               body='真实原文。' * 100, published_at=None, tier='T1', selection_threshold=60)
    with pytest.raises(ValueError, match='insufficient_real_materials'):
        packet.make_packet([dict(row, material_id=str(i)) for i in range(130)])


def test_original_database_is_opened_readonly(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises((sqlite3.OperationalError, FileNotFoundError)):
        packet.read_materials(path)
    assert not path.exists()


def test_html_data_cannot_escape_script_or_leak_private_manifest():
    data = {'schema_version': 1, 'packet_id': 'test', 'cases': [{'title': '</script><script>bad()</script>'}]}
    rendered = packet.render_html(data)
    assert '</script><script>bad()' not in rendered
    assert '\\u003c/script\\u003e' in rendered
    assert '%%PACKET%%' not in rendered


def test_bundle_bindings_conflicts_and_resolutions():
    case = {'case_id': 'c1', 'revision': 1, 'content_hash': 'h1'}
    data = {'schema_version': 1, 'packet_id': 'p1', 'cases': [case]}
    def vote(id, reviewer, select):
        return dict(record_id=id, case_id='c1', revision=1, content_hash='h1', reviewer=reviewer,
                    updated_at='2026-11-09T00:00:00Z', confirmed=True,
                    gold=dict(relevance='direct', select=select, primary_topic='practice',
                              evidence_level='announcement', reason='有可核对的技术动作'))
    bundle = dict(schema_version=1, packet_id='p1', records=[vote('a','甲','select'),vote('b','乙','reject')],
                  drafts=[], resolutions=[])
    packet.validate_bundle(data, bundle)
    assert packet.consensus(data, bundle)['c1']['status'] == 'conflict'
    bundle['resolutions'] = [dict(resolution_id='r1',case_id='c1',reviewer='负责人', reason='复核原文决定',
                                  record_ids=['a','b'],chosen_record_id='a',updated_at='2026-11-09T01:00:00Z')]
    assert packet.consensus(data, bundle)['c1']['status'] == 'resolved'
    bundle['records'][0]['content_hash'] = 'wrong'
    with pytest.raises(ValueError, match='binding'):
        packet.validate_bundle(data,bundle)


def test_returned_html_carries_results_without_executing_scripts(tmp_path):
    target = tmp_path/'returned.html'
    bundle = {'schema_version':1,'packet_id':'p','records':[],'drafts':[],'resolutions':[]}
    target.write_text('<script>throw new Error("must not run")</script>'
                      '<script type="application/json" id="embedded-review">'+json.dumps(bundle)+'</script>',encoding='utf-8')
    assert packet.read_reviews(target) == bundle
    target.write_text('<html>original unannotated file</html>',encoding='utf-8')
    with pytest.raises(ValueError,match='annotated_html_required'):
        packet.read_reviews(target)


def test_browser_and_python_share_millisecond_timestamp_precision():
    assert packet._timestamp('2026-11-09T00:00:00.000001Z') == packet._timestamp('2026-11-09T00:00:00.000002Z')
    with pytest.raises(ValueError,match='invalid_timestamp'):
        packet._timestamp('2026-02-30T00:00:00Z')
    with pytest.raises(ValueError,match='invalid_timestamp'):
        packet._timestamp('2026-01-30T00:00:00+00:99')


def test_frozen_original_and_splits_cannot_be_silently_changed(tmp_path):
    rows = [dict(material_id=str(i),revision=1,content_hash=str(i),source_slug=f's{i%5}',
                 source_name='来源',source_type='rss',language='zh' if i<40 else 'en',
                 title=f'独立文章 {i}',source_url=f'https://example.test/{i}',published_at=None,
                 body=f'Original evidence {i}. '*30,tier='T1',selection_threshold=60) for i in range(150)]
    data,manifest=packet.make_packet(rows)
    packet.atomic_json(tmp_path/'packet.json',data)
    packet.atomic_json(tmp_path/'manifest.private.json',manifest)
    packet.load_packet(tmp_path)
    data['cases'][0]['body']='Changed without a new revision'
    packet.atomic_json(tmp_path/'packet.json',data)
    with pytest.raises(ValueError,match='frozen_material_changed'):
        packet.load_packet(tmp_path)
    data,manifest=packet.make_packet(rows)
    first,second=next(k for k,v in manifest['splits'].items() if v=='development'),next(k for k,v in manifest['splits'].items() if v=='holdout')
    manifest['splits'][first],manifest['splits'][second]='holdout','development'
    packet.atomic_json(tmp_path/'packet.json',data)
    packet.atomic_json(tmp_path/'manifest.private.json',manifest)
    with pytest.raises(ValueError,match='manifest_split_mismatch'):
        packet.load_packet(tmp_path)
