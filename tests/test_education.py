"""Offline fixtures test contracts and policies, never claim live AI accuracy."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from core import education as e, classroom as c, math_tools

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))

def report(sub,wrong=None,overall='error_found'):
    return {'topic':sub['topic'],'knowledge_points':['局部规则'],'method_summary':'离线结构测试','overall':overall,
        'final_answer_status':'incorrect' if wrong else 'uncertain',
        'steps':[{'number':i,'verdict':'incorrect' if i==wrong else 'correct','observation':'离线测试依据','evidence_quote':line}
                 for i,line in enumerate(sub['steps'],1)],
        'first_error_step':wrong,'error_patterns':[{'label':'规则遗漏','step_numbers':[wrong],'severity':2,'evidence_quote':sub['steps'][wrong-1]}] if wrong else [],
        'hypotheses':[{'id':'H1','description':'待确认原因','support':['原作答'],'against':[],'open_questions':['是否能说明规则？']}],
        'uncertainties':[],'recommendation':'用新题验证'}

def setup():
    w=c.new_workspace()
    sub=e.normalize_submission(CASES[10])
    w['submissions'].append(sub)
    e.analyze_submission(sub,lambda *a,**kw:report(sub,2))
    c.review(w,sub['id'],'confirm','分配律遗漏',['分配律'],'需说明两项都乘2','review-1',first_error_step=2)
    task=c.assign(w,sub['id'],'检查分配律与负数迁移','deep','assign-1')
    sub=w['submissions'][0]
    learning=e.new_learning(task,sub)
    w['learning'].append(learning)
    return w,sub,task,learning

@pytest.mark.parametrize('case',CASES,ids=lambda r:r['question_no'])
def test_all_modules_enter_ai_without_tool_gate(case):
    sub=e.normalize_submission(case)
    called=[]
    def api(*a,**kw):
        called.append(kw)
        return report(sub,case['gold']['first_error_step'],case['gold']['overall'])
    result=e.analyze_submission(sub,api)
    assert result['status']=='completed'
    assert called[0]['purpose']=='diagnosis'
    assert set(e.TOPICS)=={case['topic'] for case in CASES}

def test_cache_versions_and_failure_preservation():
    sub=e.normalize_submission(CASES[0])
    count=[]
    def api(*a,**kw):
        count.append(1)
        return report(sub,1)
    first=e.analyze_submission(sub,api)
    assert e.analyze_submission(sub,api)['id']==first['id']
    assert len(count)==1
    second=e.analyze_submission(sub,api,True)
    assert len(count)==2 and second['id']!=first['id']
    def fail(*a,**kw):
        raise RuntimeError('offline network failure')
    assert e.analyze_submission(sub,fail,True)['status']=='failed'
    assert e.latest_success(sub)['id']==second['id']

def test_evidence_quote_and_first_error_are_checked():
    sub=e.normalize_submission(CASES[0])
    p=report(sub,1)
    p['steps'][0]['evidence_quote']='凭空编造'
    with pytest.raises(ValueError,match='原始步骤'):
        e.validate_analysis(p,sub)
    p=report(sub,1)
    p['first_error_step']=None
    with pytest.raises(ValueError,match='首个错误'):
        e.validate_analysis(p,sub)

def test_equation_first_error_and_later_valid_steps():
    tool=math_tools.evidence(e.normalize_submission(CASES[10]))
    assert [r['verdict'] for r in tool['checks']]==['correct','incorrect','correct','correct']
    assert tool['final_answer_status']=='incorrect'
    assert math_tools.evidence(e.normalize_submission(CASES[7]))['status']=='not_applicable'

def test_correct_final_does_not_erase_wrong_steps():
    sub=e.normalize_submission(CASES[11])
    p=report(sub,1)
    p['final_answer_status']='correct'
    out=e.validate_analysis(p,sub)
    assert out['first_error_step']==1 and out['overall']=='error_found'

def test_review_statistics_and_task_history():
    w,sub,task,learning=setup()
    groups=e.class_insights(w)
    assert groups[0]['confirmed']==1
    taskid=task['id']
    assert c.assign(w,sub['id'],'检查分配律与负数迁移','deep','assign-1')['id']==taskid
    c.review(w,sub['id'],'modify','修改后的标签',['等价变形'],'补充说明','review-2')
    assert len(w['reviews'])==2
    assert w['tasks'][0]['status']=='needs_recheck'
    assert e.class_insights(w)[0]['label']=='修改后的标签'
    c.review(w,sub['id'],'reject','不采纳',[],'证据不足','review-3')
    assert not e.class_insights(w)

def test_cannot_assign_unreviewed_and_idempotent_commit():
    w=c.new_workspace()
    sub=e.normalize_submission(CASES[0]);w['submissions'].append(sub)
    with pytest.raises(ValueError,match='教师确认'):
        c.assign(w,sub['id'],'目标','deep','a')
    assert c.commit(w,'once',lambda v:v['tasks'].append({'id':'fixture','submission_id':sub['id'],'student_id':sub['student_id']}))
    assert not c.commit(w,'once',lambda v:v['tasks'].append({'id':'duplicate'}))
    assert len(w['tasks'])==1

def tutor(*args,**kwargs):
    return {'message':'离线提示','purpose':'检查是否理解分配律','next_action':'hint',
            'hypothesis_updates':[{'id':'H1','support':['学生新回答'],'against':[],'status':'supported'}]}

def test_four_hints_hypothesis_updates_and_self_report_not_mastery():
    w,sub,task,l=setup()
    for level in range(1,5):
        e.tutor_turn(l,task,sub,'hint','',tutor,'hint-'+str(level))
        assert l['hint_level']==level
    e.tutor_turn(l,task,sub,'reply','我懂了',tutor,'reply')
    assert e.learning_state([]).startswith('证据不足')
    assert l['hypothesis_history'] and l['hypotheses'][0]['status']=='supported'

def exercise(*args,**kwargs):
    return {'objective':'检查负数因子分配','relation_to_error':'两个括号项都要乘负数','structure_change':'外部正系数改为负数，要求分配与符号处理',
        'question':'解方程-2*(x-4)=6','reference_steps':['-2*x+8=6','-2*x=-2','x=1'],
        'answer':'x=1','topic':'综合应用与证明','task_type':'equation','tool_expression':'',
        'knowledge_points':['分配律','符号运算'],'transfer_kind':'changed_structure','uncertainties':[]}

def grade(*args,**kwargs):
    return {'verdict':'correct','final_answer_status':'correct','explanation':'测试作答与局部解集一致','first_error_step':None,'uncertainties':[]}

def test_exercise_reference_grade_independence_and_dedup():
    w,sub,task,l=setup()
    ex=e.generate_exercise(l,task,sub,exercise)
    assert ex['reference_tool']['final_answer_status']=='correct'
    calls=[]
    def api(*a,**kw):
        calls.append(1)
        return grade()
    first=e.grade_attempt(l,task,'x=1','-2*x+8=6\n-2*x=-2\nx=1',api)
    assert first['independent'] and first['independently_verified']
    assert '当前迁移验证' in e.learning_state([first])
    assert e.grade_attempt(l,task,'x=1','-2*x+8=6\n-2*x=-2\nx=1',api,[first])['id']==first['id']
    assert len(calls)==1
    ex['answer_revealed']=True
    after=e.grade_attempt(l,task,'x=1','',grade)
    assert not after['independent'] and '提示下' in e.learning_state([after])

def test_wrong_generated_reference_is_not_published():
    w,sub,task,l=setup()
    def broken(*a,**kw):
        p=exercise()
        p['answer']='x=99'
        return p
    with pytest.raises(ValueError,match='参考解'):
        e.generate_exercise(l,task,sub,broken)
    assert l['exercise'] is None

def test_conflict_requires_review():
    w,sub,task,l=setup()
    e.generate_exercise(l,task,sub,exercise)
    def wrong_model(*a,**kw):
        return dict(grade(),verdict='incorrect',final_answer_status='incorrect')
    item=e.grade_attempt(l,task,'x=1','',wrong_model)
    assert item['conflict'] and item['verdict']=='uncertain'
    assert '等待' in e.learning_state([item])

def test_unknown_ocr_identity_not_guessed():
    def api(*a,**kw):
        return {'transcription':'匿名作业','warnings':['编号不清'],'records':[{'student_id':'','question_no':'1',
            'question':'解方程x+1=2','steps':['x=1'],'answer':'x=1','topic':'综合应用与证明','uncertainties':['编号缺失']}]}
    import io
    from PIL import Image
    out=io.BytesIO();Image.new('RGB',(30,30),'white').save(out,format='PNG')
    draft=e.extract_image(out.getvalue(),api)
    assert draft['records'][0]['student_id']==''
    with pytest.raises(ValueError,match='编号'):
        e.normalize_submission(draft['records'][0])

def test_task_package_only_target_and_feedback_not_trusted():
    w,sub,task,l=setup()
    w['submissions'].append(e.normalize_submission(CASES[0]))
    packet=e.task_package(w,task)
    assert CASES[0]['student_id'] not in json.dumps(packet,ensure_ascii=False)
    other=c.new_workspace()
    e.import_task_package(other,json.dumps(packet).encode())
    e.import_task_package(other,json.dumps(packet).encode())
    assert len(other['tasks'])==1 and len(other['submissions'])==1
    e.generate_exercise(l,task,sub,exercise)
    attempt=e.grade_attempt(l,task,'x=1','',grade)
    other['attempts'].append(attempt)
    feedback=e.feedback_package(other,other['tasks'][0])
    assert e.import_feedback(w,json.dumps(feedback).encode())==1
    assert e.import_feedback(w,json.dumps(feedback).encode())==0
    assert w['attempts'][0]['independent'] is False

def test_workspace_roundtrip_and_corrupt_file_preserved(tmp_path):
    w,sub,task,l=setup()
    path=tmp_path/'workspace.json'
    c.save(w,path)
    restored=c.load(path)
    assert restored['tasks'][0]['id']==task['id']
    path.write_text('broken',encoding='utf-8')
    with pytest.raises(ValueError):
        c.load(path)
    assert path.read_text()=='broken'


def test_task_export_drops_whole_sheet_other_students():
    w,sub,task,l=setup()
    sub['image_ref']='a'*64
    sub['transcription']='整页包括 OTHER-STUDENT 的作答'
    other=e.normalize_submission(CASES[0])
    other['image_ref']=sub['image_ref']
    w['submissions'].append(other)
    packet=e.task_package(w,task)
    assert 'OTHER-STUDENT' not in json.dumps(packet)
    assert packet['submission']['image_ref'] is None
    assert e.student_material(w,sub)['image_ref'] is None

def test_stale_snapshot_never_overwrites_disk(tmp_path):
    w,sub,task,l=setup()
    path=tmp_path/'shared-local.json'
    c.save(w,path)
    first,second=c.load(path),c.load(path)
    first['tasks'][0]['status']='completed'
    c.save(first,path)
    second['tasks'][0]['status']='assigned'
    with pytest.raises(ValueError,match='另一会话'):
        c.save(second,path)
    assert c.load(path)['tasks'][0]['status']=='completed'

def test_same_review_submit_does_not_freeze_task_again():
    w,sub,task,l=setup()
    old=len(w['reviews'])
    c.review(w,sub['id'],'confirm','分配律遗漏',['分配律'],'需说明两项都乘2','another-submit',first_error_step=2)
    assert len(w['reviews'])==old
    assert w['tasks'][0]['status']=='assigned'

def test_number_only_variants_are_rejected():
    w,sub,task,l=setup()
    def same(*a,**kw):
        p=exercise()
        p.update(question='解方程3*(x+2)=18',answer='x=4',reference_steps=['3*x+6=18','x=4'])
        return p
    with pytest.raises(ValueError,match='替换数字'):
        e.generate_exercise(l,task,sub,same)

@pytest.mark.parametrize('payload',[[],None,'not an object'])
def test_invalid_model_shapes_are_clean_errors(payload):
    w,sub,task,l=setup()
    with pytest.raises(ValueError):
        e.tutor_turn(l,task,sub,'hint','',lambda *a,**kw:payload,'bad')
    with pytest.raises(ValueError):
        e.generate_exercise(l,task,sub,lambda *a,**kw:payload)


def test_cross_question_pattern_keeps_original_labels_and_severity():
    w=c.new_workspace()
    for index in (1,13):
        sub=e.normalize_submission(CASES[index])
        p=report(sub,CASES[index]['gold']['first_error_step'])
        p['error_patterns'][0]['label']='原始诊断措辞'+str(index)
        p['error_patterns'][0]['severity']=3
        e.analyze_submission(sub,lambda *a,_p=p,**kw:_p)
        w['submissions'].append(sub)
    groups=e.class_insights(w)
    target=next(g for g in groups if g['label']=='遗漏内层导数（工具观察模式）')
    assert len(target['submission_ids'])==2
    assert target['repeat_students']==['A02']
    assert len(target['original_labels'])==2
    assert target['severity']==3
