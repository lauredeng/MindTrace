"""Real SymPy calculations, domain traps, and hostile input boundaries."""
from copy import deepcopy
import json
import pytest
from core import math_kernel as m, exercise_review as r, education as e, agent as a
from test_education import setup, exercise
from test_agent import workspace, decision


CASES = [
    ({'operation':'derivative','expression':'log(x)-a*x','expected':'1/x-a'}, 'correct'),
    ({'operation':'derivative','expression':'exp(x)*sin(x)','expected':'exp(x)*(sin(x)+cos(x))'}, 'correct'),
    ({'operation':'derivative','expression':'sqrt(x)','expected':'1/(2*sqrt(x))'}, 'correct'),
    ({'operation':'derivative','expression':'log(x)','expected':'x'}, 'unresolved'),
    ({'operation':'equation','expression':'sin(2*x)=sqrt(3)/2','domain':{'lower':'0','upper':'pi'},'expected':['pi/6','pi/3']}, 'correct'),
    ({'operation':'equation','expression':'log(x)=1','expected':['E']}, 'correct'),
    ({'operation':'equation','expression':'sqrt(x+1)=x-1','expected':['3']}, 'correct'),
    ({'operation':'equation','expression':'sqrt(x+1)=x-1','expected':['0','3']}, 'incorrect'),
    ({'operation':'equation','expression':'(x**2-1)/(x-1)=2','expected':[]}, 'correct'),
    ({'operation':'equation','expression':'x**2/x=0','expected':['0']}, 'incorrect'),
    ({'operation':'inequality','expression':'1/x-2>0','expected':{'lower':'0','upper':'1/2','left_open':True,'right_open':True}}, 'correct'),
    ({'operation':'inequality','expression':'log(x)>0','expected':{'lower':'1','upper':'oo','left_open':True,'right_open':True}}, 'correct'),
    ({'operation':'sum','expression':'k*2**k','variable':'k','lower':'1','upper':'n','expected':'(n-1)*2**(n+1)+2'}, 'correct'),
    ({'operation':'sum','expression':'k**2','variable':'k','lower':'1','upper':'n','expected':'n*(n+1)*(2*n+1)/6'}, 'correct'),
    ({'operation':'evaluate','expression':'sin(pi/12)**2','expected':'(2-sqrt(3))/4'}, 'correct'),
    ({'operation':'evaluate','expression':'binomial(5,2)*binomial(3,1)/binomial(8,3)','expected':'15/28'}, 'correct'),
    ({'operation':'evaluate','expression':'binomial(10,3)*(1/3)**3*(2/3)**7','expected':'5120/19683'}, 'correct'),
    ({'operation':'evaluate','expression':'1/4+2/4+3/4','expected':'3/2'}, 'correct'),
    ({'operation':'dot','left':['1','2','-1'],'right':['2','0','2'],'expected':'0'}, 'correct'),
    ({'operation':'cross','left':['1','0','0'],'right':['0','1','0'],'expected':['0','0','1']}, 'correct'),
    ({'operation':'norm','left':['1','1','1'],'expected':'sqrt(3)'}, 'correct'),
    ({'operation':'distance','left':['-sqrt(2)','-sqrt(2)/2'],'right':['sqrt(2)','sqrt(2)/2'],'expected':'sqrt(10)'}, 'correct'),
    ({'operation':'system','variables':['x','y'],'equations':['x**2/4+y**2=1','y=x/2'],
      'expected':[['-sqrt(2)','-sqrt(2)/2'],['sqrt(2)','sqrt(2)/2']]}, 'correct'),
    ({'operation':'set','left':['-2','-1','0','1','2'],'right':['-1','0','3'],'expected':['-1','0']}, 'correct'),
]


@pytest.mark.parametrize('spec,expected', CASES)
def test_highschool_computations(spec, expected):
    result=m.check(spec)
    assert result.get('verdict')==expected, result
    assert result['engine']==m.VERSION
    if expected!='unresolved':assert result['status']=='checked'


@pytest.mark.parametrize('expression', ["__import__('os').system('whoami')", 'x.__class__',
    '[x for x in (1,2)]', '(lambda:1)()', 'open("private.txt")', 'factorial(1000000)',
    '2**1000000', 'sin(x,2)', '1/0', 'float("nan")', 'x[0]'])
def test_unsafe_and_excessive_expressions_are_never_executed(expression):
    result=m.check({'operation':'evaluate','expression':expression,'expected':'1'})
    assert result['status'] in ('unsupported','unresolved') and result.get('verdict')!='correct'


def test_deadline_and_defensive_cached_copy():
    request={'operation':'evaluate','expression':'sqrt(3)','expected':'sqrt(3)'}
    assert m.check(request,timeout=0.00001)['status']=='timeout'
    first=m.check(request);first['limitations'].append('tamper')
    assert 'tamper' not in m.check(request)['limitations']


def test_domain_holes_and_unresolved_parameters_are_not_fabricated_passes():
    assert m.check({'operation':'derivative','expression':'x','expected':'x/x'})['verdict']=='unresolved'
    result=m.check({'operation':'derivative','expression':'sqrt(x)','expected':'1/(2*sqrt(x))'})
    assert result['domain']=='Interval.open(0, oo)'
    assert m.check({'operation':'inequality','expression':'a*x>1'})['status']=='unsupported'
    assert m.check({'operation':'system','variables':['x'],'equations':['x/x=1'],'expected':[['1']]})['status']=='unsupported'
    assert m.check({'operation':'equation','variable':'n','expression':'n+1=0','expected':[]})['verdict']=='correct'


def reviewer(**changes):
    return dict({'verdict':'correct','independent_answer':'正确参考结论',
        'checks':dict.fromkeys(r.FIELDS,'pass'),'reason':'测试提供的独立复核回执，仅验证控制流程。','issues':[]},**changes)


def trig_exercise():
    ex=exercise()
    ex.update(question='解方程 sin(2*x)=sqrt(3)/2，其中 0≤x≤pi。',
        answer='pi/6, pi/3',reference_steps=['sin(2*x)=sqrt(3)/2','x=pi/6 或 x=pi/3'],
        task_type='general',topic='三角函数',answer_format='set',question_type='解答题',
        rubric=['将2x限制在[0,2pi]内','两支解均保留','回代检验'],
        math_request=dict(CASES[4][0],source_quote='sin(2*x)=sqrt(3)/2'))
    return ex


def test_structured_exercise_generation_review_and_student_check_are_separate():
    w,sub,task,learning=setup();calls=[]
    def model(system,user,**kw):
        calls.append(kw['purpose'])
        if kw['purpose']=='exercise':return trig_exercise()
        if kw['purpose']=='reference_review':return reviewer()
        return {'verdict':'correct','final_answer_status':'correct','explanation':'离线过程评审结果',
                'first_error_step':None,'uncertainties':[]}
    ex=e.generate_exercise(learning,task,sub,model)
    assert ex['validation']['status']=='symbolic_and_ai_reviewed'
    assert e.generate_exercise(learning,task,sub,model) is ex
    good=e.grade_attempt(learning,task,'["pi/6","pi/3"]',[],model)
    assert good['tool']['final_answer_status']=='correct'
    bad=e.grade_attempt(learning,task,'["pi/6"]',[],model)
    assert bad['tool']['final_answer_status']=='incorrect' and bad['conflict']
    assert calls.count('exercise')==calls.count('reference_review')==1


def test_same_structure_allowed_but_not_mislabeled_as_transfer():
    w,sub,task,learning=setup()
    def model(*args,**kw):
        if kw['purpose']=='reference_review':return reviewer()
        ex=exercise();ex.update(question='解方程3*(x+2)=18',answer='x=4',reference_steps=['x=4'],transfer_kind='same_structure')
        return ex
    assert e.generate_exercise(learning,task,sub,model)['transfer_kind']=='same_structure'


def test_proof_can_be_published_after_review_without_fake_symbolic_proof():
    w,sub=workspace()
    a.run(w,sub['id'],'A',lambda *args,**kw:decision('offer_practice','验证均值不等式的适用条件。'))
    def model(*args,**kw):
        if kw['purpose']=='reference_review':return reviewer(independent_answer='a+b≥2√ab，等号当且仅当a=b')
        ex=exercise();ex.update(question='已知a,b为正实数，证明a+b≥2√ab并给出等号条件。',
            answer='a+b≥2√ab，等号当且仅当a=b',reference_steps=['(√a-√b)^2≥0','a+b≥2√ab，等号当且仅当a=b'],
            task_type='general',answer_format='proof',topic='不等式',rubric=['正数条件','完全平方非负','等号条件'])
        return ex
    practice=a.accept_practice(w,sub['id'],'A',model)
    ex=practice['learning']['exercise']
    assert ex['validation']['status']=='ai_reviewed'
    assert a.latest_run(w,sub['id'],'A')['status']=='waiting_practice'
    assert ex['reference_review']['formal_proof'] is False


def test_review_failure_does_not_regenerate_or_release_question():
    w,sub,task,learning=setup();calls=[]
    def model(*args,**kw):
        calls.append(kw['purpose'])
        if kw['purpose']=='exercise':return trig_exercise()
        if calls.count('reference_review')==1:raise RuntimeError('offline timeout')
        return reviewer()
    with pytest.raises(RuntimeError):e.generate_exercise(learning,task,sub,model)
    assert learning['exercise'] is None and learning['pending_exercise']
    assert e.generate_exercise(learning,task,sub,model)
    assert calls==['exercise','reference_review','reference_review']


def test_incomplete_or_conflicting_review_blocks_publication():
    for receipt in (reviewer(checks=dict.fromkeys(r.FIELDS,'uncertain')),reviewer(issues=['缺少等号条件']),reviewer(verdict='incorrect')):
        w,sub,task,learning=setup()
        def model(*args,**kw):return trig_exercise() if kw['purpose']=='exercise' else receipt
        with pytest.raises(ValueError,match='未发布'):e.generate_exercise(learning,task,sub,model)
        assert learning['exercise'] is None


def test_agent_calls_broad_tools_without_claiming_model_binding_proved():
    w,sub=workspace();sub['question']='解方程 sin(2*x)=sqrt(3)/2，其中0≤x≤pi。'
    def model(system,user,**kw):
        data=json.loads(user)
        if not data['observations']:
            return decision('verify_math','',step=None,evidence_ids=['QUESTION'],math_request=trig_exercise()['math_request'])
        observed=next(iter(data['observations'].values()))
        assert observed['calculation']['verdict']=='correct'
        assert observed['model_binding']=='requires_reasoning_review'
        assert 'final_answer_status' not in observed
        return decision('explain_step','在指定区间内有两支解。',step=None,evidence_ids=['QUESTION'])
    result=a.run(w,sub['id'],'A',model)
    assert result['status']=='delivered' and result['tool_calls']==1


def test_agent_rejects_tools_without_real_source_quote():
    w,sub=workspace()
    result=a.run(w,sub['id'],'A',lambda *args,**kw:decision('verify_math','',math_request=trig_exercise()['math_request']))
    assert result['tool_calls']==0 and result['status']=='stopped'


@pytest.mark.parametrize('answer', ['π/6，π/3', '{pi/6,pi/3}', 'x=pi/6或x=pi/3'])
def test_sets_accept_student_notation_without_json(answer):
    assert r.student_tool(trig_exercise(),answer)['final_answer_status']=='correct'


def test_multiple_select_compares_sets_and_never_calls_it_formal_validation():
    ex={'question_type':'多选题','answer':'AC','options':{'A':'a','B':'b','C':'c'}}
    assert r.student_tool(ex,'C、A')['final_answer_status']=='correct'
    assert r.student_tool(ex,'A')['final_answer_status']=='incorrect'
    assert r.student_tool(ex,'AB')['final_answer_status']=='incorrect'
    assert r.student_tool(ex,'AD')['status']=='unsupported'
    assert r.student_tool(ex,'AC')['authority']=='ai_reference'


def test_reference_pattern_computations_cover_every_topic():
    from core.question_patterns import examples
    for topic in e.TOPICS:
        patterns=examples(topic)
        assert patterns and patterns[0]['rubric']
        spec=patterns[0]['math_request']
        if spec:assert m.check(spec).get('verdict')=='correct',patterns[0]
        patterns[0]['rubric'].clear()
        assert examples(topic)[0]['rubric']


def test_changed_question_invalidates_reference_review_before_student_grading():
    w,sub,task,learning=setup()
    ex=e.generate_exercise(learning,task,sub,exercise)
    ex['question']='被修改的另一道题'
    with pytest.raises(ValueError,match='重新复核'):
        e.grade_attempt(learning,task,'1',[],lambda *args,**kw:pytest.fail('Stale reference reached model'))
