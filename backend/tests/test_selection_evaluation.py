import pytest

from bluepulse_backend import selection_evaluation as evaluation


def passing_decision(data):
    return {'label':'PASS','relevance':'direct','reason':'具体技术应用','evidence':data['text'][:30]}


@pytest.mark.parametrize('status',['pending','conflict'])
def test_missing_gold_precedes_credentials_and_output(tmp_path, monkeypatch, status):
    monkeypatch.setattr(evaluation, 'load_packet', lambda path: ({'packet_id':'p','cases':[{'case_id':'a'}]}, {'splits':{'a':'development'}}))
    monkeypatch.setattr(evaluation, 'consensus', lambda *args: {'a':{'status':status,'gold':None}})
    monkeypatch.setattr(evaluation, 'preset_paths', lambda: pytest.fail('credentials/config must not be read'))
    reviews = tmp_path / 'reviews.json'
    reviews.write_text('{}')
    with pytest.raises(ValueError, match='incomplete_or_conflicting_gold'):
        evaluation.run(tmp_path, reviews, tmp_path / 'output', allow_paid=True)
    assert not (tmp_path / 'output').exists()


def test_holdout_requires_explicit_confirmation_before_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'load_packet', lambda path: pytest.fail('holdout guard first'))
    with pytest.raises(ValueError, match='holdout_confirmation_required'):
        evaluation.run(tmp_path, tmp_path / 'reviews', tmp_path / 'output', split='holdout', allow_paid=True)


def test_confirmed_only_uses_finalized_cases_from_the_requested_split(tmp_path, monkeypatch):
    cases = [{'case_id':key} for key in ('confirmed', 'pending', 'held')]
    manifest = {'splits':{'confirmed':'development','pending':'development','held':'holdout'}}
    monkeypatch.setattr(evaluation,'load_packet',lambda path:({'cases':cases},manifest))
    monkeypatch.setattr(evaluation,'read_reviews',lambda path:{})
    monkeypatch.setattr(evaluation,'consensus',lambda *_:{
        'confirmed':{'status':'confirmed'},'pending':{'status':'pending'},'held':{'status':'confirmed'}})
    _, _, selected, decisions = evaluation.chosen_gold(tmp_path, None, 'development', False, confirmed_only=True)
    assert selected == [cases[0]] and list(decisions) == ['confirmed']


def test_exact_production_inputs_two_independent_scores_and_resume():
    calls = []
    def step(capability, purpose, prompt, data, tokens):
        calls.append((capability,purpose,data))
        if capability == 'prefilter':
            return passing_decision(data), {}
        return {'content_type':'research_paper','sig':8,'nov':8,'cred':8,'reson':8,'act':8}, {'request_id':purpose}
    case = {'title':'Original title','body':'x'*13000,'body_status':'full_text'}
    state = evaluation.evaluate_case(case, step, 70)
    assert state['scores'] == [80,80] and state['prediction'] is True
    assert [c[1] for c in calls] == ['prefilter','score:1','score:2']
    assert calls[0][2] == {'title':'Original title','text':'x'*12000,'bodyStatus':'full_text'}
    assert evaluation.evaluate_case(case, step, 70, previous=state) == state
    assert len(calls) == 3


def test_missing_body_block_becomes_unknown_without_scores():
    state = evaluation.evaluate_case({'title':'Title','body':'','body_status':'metadata_only'},
                                     lambda *args: ({'label':'BLOCK'},{}), 70)
    assert state['prefilter'] == 'UNKNOWN'
    assert state['prediction'] is None and state['status'] == 'unscored'


def test_metrics_use_full_gold_positive_denominator_and_keep_unknown_separate():
    rows = [{'gold':{'select':'select'},'prediction':True,'status':'scored'},
            {'gold':{'select':'select'},'prediction':None,'status':'failed'},
            {'gold':{'select':'reject'},'prediction':True,'status':'scored'},
            {'gold':{'select':'reject'},'prediction':None,'status':'unscored'},
            {'gold':{'select':'uncertain'},'prediction':False,'status':'blocked'}]
    metrics = evaluation.metrics(rows)
    assert metrics['precision'] == .5
    assert metrics['recall'] == .5
    assert metrics['coverage'] == .5
    assert metrics['gold_uncertain'] == 1
    assert metrics['unclassified_gold_positive'] == 1
    assert metrics['failed'] == 1 and metrics['unscored'] == 1


def test_partial_scores_are_preserved_and_duplicate_response_rejected():
    scores = {'content_type':'product_launch','sig':7,'nov':7,'cred':7,'reson':7,'act':7}
    def step(*args):
        return scores, {'request_id':'same'}
    previous = {'prefilter':'PASS','scores':[70],'request_ids':['same'],'status':'running'}
    with pytest.raises(ValueError, match='duplicate_score_response'):
        evaluation.evaluate_case({'title':'t','body':'body'}, step, 60, previous=previous)
    assert previous['scores'] == [70]

def test_only_chosen_split_is_evaluated_and_resume_does_not_repeat(tmp_path, monkeypatch):
    cases = [{'case_id':'dev','title':'t','body':'body','language':'en','source_slug':'source'},
             {'case_id':'held','title':'holdout','body':'holdout body','language':'zh','source_slug':'other'}]
    manifest = {'splits':{'dev':'development','held':'holdout'},
                'source_settings':{'dev':{'selection_threshold':70},'held':{'selection_threshold':70}}}
    data = {'packet_id':'packet','cases':cases}
    monkeypatch.setattr(evaluation,'load_packet',lambda path:(data,manifest))
    monkeypatch.setattr(evaluation,'read_reviews',lambda path:{})
    monkeypatch.setattr(evaluation,'consensus',lambda *args:{
        'dev':{'status':'confirmed','gold':{'select':'select','primary_topic':'paper'}},
        'held':{'status':'pending','gold':None}})
    monkeypatch.setattr(evaluation,'_production_model_settings',lambda:({},tmp_path/'production'/'live.db'))
    monkeypatch.setattr(evaluation,'preset_paths',lambda:{'default':tmp_path/'model.env'})
    monkeypatch.setattr(evaluation,'load_local_credentials',lambda path:('https://example.test/v1','private','model'))
    calls = []
    class FakeSteps:
        def __init__(self,*args,**kwargs):
            pass
        def __call__(self,capability,purpose,prompt,data,tokens):
            calls.append(purpose)
            assert 'holdout' not in data['title']
            if capability == 'prefilter':
                return passing_decision(data),{}
            return {'content_type':'research_paper','sig':8,'nov':8,'cred':8,'reson':8,'act':8},{'request_id':purpose}
    monkeypatch.setattr(evaluation,'Steps',FakeSteps)
    output = tmp_path/'evaluation'
    report = evaluation.run(tmp_path/'packet',tmp_path/'reviews',output,allow_paid=True)
    result = next(iter(report['models'].values()))
    assert [case['case_id'] for case in result['cases']] == ['dev']
    assert result['summary']['threshold_scan'] is not None
    assert result['summary']['can_calibrate'] is False
    assert result['usage']['attempts_total'] == 0
    evaluation.run(tmp_path/'packet',tmp_path/'reviews',output,allow_paid=True)
    assert calls == ['prefilter','score:1','score:2']
    assert not (tmp_path/'production').exists()


def test_holdout_summary_never_scans_thresholds():
    assert evaluation.summarize([],scan=False)['threshold_scan'] is None


def test_paid_model_default_is_closed_after_consensus(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation,'chosen_gold',lambda *args, **kwargs:({}, {}, [], {}))
    monkeypatch.setattr(evaluation,'_production_model_settings',lambda:pytest.fail('no config before explicit paid opt-in'))
    with pytest.raises(ValueError,match='explicit_paid_model_opt_in_required'):
        evaluation.run(tmp_path,tmp_path/'reviews',tmp_path/'output')
    assert not (tmp_path/'output').exists()

def test_real_steps_use_isolated_durable_budget_and_keep_partial_score(tmp_path, monkeypatch):
    import json
    import httpx
    case = {'case_id':'dev','title':'Original','body':'Original body','language':'en','source_slug':'source'}
    data = {'packet_id':'packet','cases':[case]}
    manifest = {'splits':{'dev':'development'},'source_settings':{'dev':{'selection_threshold':70}}}
    monkeypatch.setattr(evaluation,'load_packet',lambda path:(data,manifest))
    monkeypatch.setattr(evaluation,'read_reviews',lambda path:{})
    monkeypatch.setattr(evaluation,'consensus',lambda *args:{'dev':{'status':'confirmed','gold':{'select':'select','primary_topic':'paper'}}})
    monkeypatch.setattr(evaluation,'_production_model_settings',lambda:({},tmp_path/'production'/'live.db'))
    config = tmp_path/'model.env'
    config.write_text('base_url=https://example.test/v1\nkey=private-key\nllm_id=mock-model\n')
    monkeypatch.setattr(evaluation,'preset_paths',lambda:{'default':config})
    requests = []
    def transport(request):
        assert request.method == 'POST' and request.url.path == '/v1/chat/completions'
        requests.append(request)
        payload = json.loads(request.content)
        result = passing_decision(json.loads(payload['messages'][1]['content'])) if payload['messages'][0]['content'] == evaluation.editorial.PREFILTER else {
            'content_type':'research_paper','sig':8,'nov':8,'cred':8,'reson':8,'act':8}
        return httpx.Response(200,json={'id':f'request-{len(requests)}','model':'mock-model',
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,'input_tokens':10,'output_tokens':5},
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]})
    real_client = httpx.Client
    monkeypatch.setattr(evaluation.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(transport),**kwargs))
    output = tmp_path/'evaluation'
    report = evaluation.run(tmp_path/'packet',tmp_path/'reviews',output,allow_paid=True,max_calls=2)
    result = next(iter(report['models'].values()))
    assert result['cases'][0]['scores'] == [80]
    assert result['cases'][0]['status'] == 'failed'
    assert result['cases'][0]['error'] in {'request_budget_60','request_budget_total'}
    assert result['usage']['attempts_total'] == 2
    assert result['usage']['by_model']['mock-model']['attempts'] == 2
    assert result['usage']['prompt_tokens'] == 20
    assert result['usage']['completion_tokens'] == 10
    assert result['usage']['total_tokens'] == 30
    assert result['usage']['by_model']['mock-model']['total_tokens'] == 30
    assert result['usage']['duration_reported_attempts'] == 2
    assert result['usage']['usage_reported_attempts'] == 2
    evaluation.run(tmp_path/'packet',tmp_path/'reviews',output,allow_paid=True,max_calls=2)
    assert len(requests) == 2
    assert not (tmp_path/'production').exists()

def test_relevance_metrics_distinguish_false_positives_and_unresolved_cases():
    rows = [{'gold':{'relevance':'direct'},'prefilter':'UNKNOWN','status':'scored'},
            {'gold':{'relevance':'potential'},'status':'failed'},
            {'gold':{'relevance':'irrelevant'},'prefilter':'PASS','status':'scored'},
            {'gold':{'relevance':'uncertain'},'prefilter':'BLOCK','status':'blocked'}]
    result = evaluation.prefilter_metrics(rows)
    assert result['precision'] == 0 and result['recall'] == 0
    assert result['coverage'] == 1/3
    assert result['gold_uncertain'] == 1 and result['failed'] == 1
    assert result['scope'] == 'publication_relevance_gate' and result['undecided'] == 1


def test_cli_exit_is_nonzero_for_incomplete_case(tmp_path,monkeypatch):
    monkeypatch.setattr(evaluation,'run',lambda *args,**kwargs:{'models':{'m':{'cases':[{'status':'unknown'}]}}})
    arguments = ['--packet-dir',str(tmp_path),'--reviews',str(tmp_path/'reviews.html'),'--output-dir',str(tmp_path/'out')]
    assert evaluation.main(arguments) == 1
    monkeypatch.setattr(evaluation,'run',lambda *args,**kwargs:{'models':{'m':{'cases':[{'status':'scored'}]}}})
    assert evaluation.main(arguments) == 0
