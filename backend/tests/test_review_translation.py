from bluepulse_backend.review_translation import translate_case


def test_chinese_original_never_calls_a_model():
    case = {'case_id':'P001','language':'zh','title':'真实原文','analysis_text':'中文材料', 'assist':None}
    assert translate_case(case, lambda *args: (_ for _ in ()).throw(AssertionError('paid call')))['status'] == 'original_zh'


def test_auxiliary_translation_uses_original_not_editorial_answers():
    case = {'case_id':'P002','language':'en','title':'Original title','analysis_text':'Original body.\n\nEvidence only.',
            'zh_summary':'DO NOT USE MODEL SUMMARY','assist':None}
    calls=[]
    def step(capability,purpose,prompt,data,tokens):
        calls.append(data['blocks'][0])
        return {'blocks':[data['blocks'][0].replace('Original title','原始标题').replace('Original body.','原文正文。')]}, {}
    result = translate_case(case, step)
    assert result['status'] == 'translated'
    assert result['title_zh'] == '原始标题'
    assert '原文正文。' in result['body_zh']
    assert all('DO NOT USE' not in call for call in calls)


def test_completed_translation_is_reused_without_network():
    assist = {'status':'translated','title_zh':'已译','body_zh':'已译正文'}
    case = {'language':'en','assist':assist}
    assert translate_case(case, None) is assist
