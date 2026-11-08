from navigation_helpers import route,main_labels
"""V1.2 UI loop with labelled offline model transport."""
import json
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from core import ai,product as p,education as e
from test_product import quick,deep,correction
from test_education import CASES
ROOT=Path(__file__).resolve().parents[1]

def click(at,label):
    next(b for b in at.button if b.label==label).click().run()
    assert not at.exception

@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv('MINDTRACE_ENV','production')
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE','0')
    monkeypatch.setattr(ai,'ai_ready',lambda:True)
    calls=[]
    def offline(messages,**kwargs):
        purpose=kwargs['purpose'];calls.append(purpose)
        raw=json.loads(messages[1]['content'])
        if purpose in ('quick_grading','error_analysis'):
            sub=e.normalize_submission(dict(raw,student_id='FIXTURE'))
            return quick(sub) if purpose=='quick_grading' else deep(sub)
        if purpose=='solve_question':
            return {'known_conditions':['方程给定'],'goal':'求未知数','method':'等价变形','correction':correction()}
        if purpose=='study_dialogue':
            return {'message':'等式两边同时乘除同一个非零数，保持相等。','purpose':'解释本题关键步骤','next_suggestion':'也可以继续追问另一种解法'}
        raise AssertionError('Unexpected offline purpose')
    monkeypatch.setattr(ai,'completion',offline)
    at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not at.exception
    return at,calls

def test_new_navigation_and_teacher_student_notebook_loop(app):
    at,calls=app
    click(at,'进入教师工作台')
    assert main_labels(at)==['作业批改','班级错误分析','历史记录']
    w=at.session_state['studio_workspace'];batch=p.create_batch(w,'UI构造批次',[CASES[10]],'constructed_examples')
    at.run();click(at,'开始批改并分析错题')
    assert calls==['quick_grading','error_analysis']
    assert len(at.session_state['studio_workspace']['notebook'])==1
    route(at,'班级学情')
    assert not at.exception
    assert any('各题错误人数' in h.value for h in at.subheader)
    assert any('作答与证据' in m.value for m in at.markdown)
    click(at,'返回产品首页');click(at,'进入学生学习中心')
    assert main_labels(at)==['AI解题与辅导','我的错题本','错因分析']
    click(at,'获取所选讲解')
    click(at,'请 AI 主动问我一个关键问题')
    next(t for t in at.text_area if t.label=='继续追问 / 回答 AI').set_value('为什么两边都要除以2？')
    click(at,'发送问题或回答')
    route(at,'我的错题本')
    assert not at.exception
    click(at,'查看解析')
    next(s for s in at.selectbox if s.label=='主要错因').set_value('解题方法选择不当')
    next(c for c in at.checkbox if c.label=='确认这次错因分类').check()
    click(at,'保存错因与个人修订')
    w=at.session_state['studio_workspace']
    assert w['notebook'][0]['primary_category']=='解题方法选择不当'
    assert w['notebook'][0]['ai_category']=='公式或定理遗忘'
    route(at,'错因分析')
    assert not at.exception
    assert at.session_state['studio_workspace']['notebook'][0]['primary_category']=='解题方法选择不当'
    assert calls.count('study_dialogue')==2
    assert not w['tasks'] and not w['attempts']

def test_no_answer_direct_solution_no_forced_task(app):
    at,calls=app;click(at,'进入学生学习中心')
    assert not any(s.label in ('匿名学习编号','新的匿名编号','我的匿名学习编号') for s in at.text_input)
    next(t for t in at.text_area if t.label=='完整题目与条件').set_value('2*(x+3)=10')
    click(at,'使用这道题')
    assert not at.exception
    at.session_state['solve_mode']='full';at.run()
    click(at,'获取所选讲解')
    assert calls==['solve_question']
    assert at.session_state['studio_workspace']['submissions'][0]['steps']==[]
    click(at,'加入 / 更新我的错题本')
    assert len(at.session_state['studio_workspace']['notebook'])==1
    assert at.session_state['studio_workspace']['notebook'][0]['primary_category']=='暂无解题思路'

def test_current_student_is_automatic_and_persists_without_public_id_ui(app):
    at,calls=app;w=at.session_state['studio_workspace']
    for sid in ('A','B'):
        w['submissions'].append(e.normalize_submission(dict(CASES[10],student_id=sid)))
    at.session_state['studio_current_student']='B'
    click(at,'进入学生学习中心')
    assert at.session_state['studio_current_student']=='B'
    at.run()
    assert not any('编号' in s.label for s in at.selectbox)
    assert not any(t.label in ('匿名学习编号','新的匿名编号','我的匿名学习编号') for t in at.text_input)
    route(at,'我的错题本')
    assert at.session_state['studio_current_student']=='B'
    assert calls==[]


def test_notebook_foreign_source_link_is_not_rendered(app):
    at,calls=app;w=at.session_state['studio_workspace']
    own=e.normalize_submission(dict(CASES[10],student_id='A'))
    foreign=e.normalize_submission(dict(CASES[10],student_id='B',steps=['FOREIGN_PRIVATE_STEP'],answer='OTHER_PRIVATE_ANSWER'))
    w['submissions'].extend([own,foreign])
    item=p.sync_notebook(w,own['id'],True,'暂无解题思路')
    item['source_ids'].append(foreign['id'])
    at.session_state['studio_current_student']='A'
    click(at,'进入学生学习中心')
    route(at,'我的错题本')
    assert not at.exception
    assert not any('FOREIGN_PRIVATE_STEP' in str(t.value) or 'OTHER_PRIVATE_ANSWER' in str(t.value) for t in at.text)
    assert calls==[]


def test_primary_navigation_settings_and_student_identity_are_clean(app):
    at,calls=app
    click(at,'进入教师工作台')
    assert main_labels(at)==['作业批改','班级错误分析','历史记录']
    assert not any('经典' in c.label for c in at.checkbox)
    assert not any('旧版' in b.label for b in at.sidebar.button)
    click(at,'返回产品首页');click(at,'进入学生学习中心')
    assert main_labels(at)==['AI解题与辅导','我的错题本','错因分析']
    identity=at.session_state['studio_current_student']
    assert identity and identity!='SELF-01'
    assert not any(identity in str(t.value) for t in at.text)
    click(at,'设置')
    assert main_labels(at)==['AI解题与辅导','我的错题本','错因分析']
    labels=[getattr(d.proto,'label','') for d in at.get('download_button')]
    assert '下载我的错题记录' in labels and '下载工作区备份' not in labels
    assert calls==[]


def test_fixed_role_switch_and_no_public_radio(app):
    at,_=app
    assert not any(s.label=='工作空间' for s in at.sidebar.selectbox)
    click(at,'学生')
    assert main_labels(at)==['AI解题与辅导','我的错题本','错因分析']
    assert not at.radio
    click(at,'我的错题本')
    assert not at.radio
    click(at,'教师')
    assert main_labels(at)==['作业批改','班级错误分析','历史记录']


def test_home_preselection_does_not_navigate_and_is_reversible(app):
    at,calls=app
    assert at.session_state['home_preselection']=='teacher'
    next(b for b in at.button if b.key=='home_select_student').click().run()
    assert at.session_state['home_preselection']=='student'
    assert at.session_state['experience_role']=='产品首页'
    next(b for b in at.button if b.key=='home_select_teacher').click().run()
    assert at.session_state['home_preselection']=='teacher'
    assert at.session_state['experience_role']=='产品首页'
    next(b for b in at.button if b.key=='home_select_student').click().run()
    click(at,'进入学生学习中心')
    assert at.session_state['experience_role']=='学生学习空间'
    assert calls==[]


@pytest.mark.parametrize('failure,expected,action',[
    ('all','failed','重试未完成的批改'),
    ('deep','partial','重试未完成的批改'),
    ('quota','paused','继续未完成的批改'),
])
def test_batch_failures_have_truthful_status_visible_retry_and_no_auto_calls(app,monkeypatch,failure,expected,action):
    from core.limits import UsageLimitError
    at,calls=app;normal=ai.completion;attempts=[]
    def unavailable(messages,**kwargs):
        attempts.append(kwargs['purpose'])
        if failure=='quota':raise UsageLimitError('操作较频繁，请稍候再试')
        if failure=='deep' and kwargs['purpose']=='quick_grading':return normal(messages,**kwargs)
        raise RuntimeError('明确的离线故障')
    monkeypatch.setattr(ai,'completion',unavailable)
    click(at,'进入教师工作台')
    w=at.session_state['studio_workspace'];b=p.create_batch(w,'故障演示验证',[CASES[10]],'constructed_examples')
    at.run();click(at,'开始批改并分析错题')
    assert at.session_state['studio_workspace']['batches'][0]['status']==expected
    assert any(button.label==action and not button.disabled for button in at.button)
    assert any('“—”' in info.value for info in at.info)==(failure!='deep')
    count=len(attempts);at.run();assert len(attempts)==count
    monkeypatch.setattr(ai,'completion',normal)
    click(at,action)
    assert at.session_state['studio_workspace']['batches'][0]['status']=='processed'
    assert calls.count('quick_grading')==1 and calls.count('error_analysis')==1
    assert not any('平均正确率显示' in info.value for info in at.info)
    from core import presentation as v
    summary=v.batch_summary(at.session_state['studio_workspace'],b['id'],automatic=True)
    assert summary['valid_count']==1 and summary['correctness']==0
    click(at,'确认这份批改')
    summary=v.batch_summary(at.session_state['studio_workspace'],b['id'])
    assert summary['valid_count']==1 and summary['correctness']==0
    assert not any('尚未完成教师复核' in info.value for info in at.info)


def test_teacher_corrects_image_transcription_and_only_regrades_that_submission(app,monkeypatch):
    import io
    from PIL import Image
    from ui.workbench import Runtime
    at,calls=app
    click(at,'进入教师工作台')
    w=at.session_state['studio_workspace']
    image_ref='a'*64
    batch=p.create_batch(w,'转写校正',[
        dict(CASES[10],image_ref=image_ref),
        dict(CASES[2],image_ref=image_ref),
    ])
    sub,other=w['submissions']
    from test_product import quick
    from core import presentation as v
    p.quick_check(sub,lambda *args,**kw:quick(sub))
    p.quick_check(other,lambda *args,**kw:quick(other,'correct'))
    v.confirm_short(w,sub['id'])
    p.sync_notebook(w,sub['id'])
    before=other['quick_checks'][0]['id']
    image=io.BytesIO()
    Image.new('RGB',(32,32),'white').save(image,format='PNG')
    monkeypatch.setattr(Runtime,'image',lambda self,ref:image.getvalue() if ref else None)
    requested=[]
    def grade(messages,**kwargs):
        import json
        body=json.loads(messages[-1]['content'])
        requested.append((kwargs['purpose'],body['answer']))
        return dict(verdict='correct',final_answer_status='correct',process_checked=True,
                    evidence_id='ANSWER',basis='正确的等价变形。')
    monkeypatch.setattr(ai,'completion',grade)
    at.session_state['heatmap_selected_'+batch['id']]=p.item_key(sub)
    at.run()
    next(widget for widget in at.text_area if widget.label=='作答步骤 · 每行一步').set_value('2*x+6=10\n2*x=4\nx=2')
    next(widget for widget in at.text_input if widget.label=='作答的最终答案').set_value('x=2')
    next(widget for widget in at.checkbox if widget.label=='我已对照原图确认转写').check()
    click(at,'保存转写并重判本题')
    w=at.session_state['studio_workspace']
    sub,other=w['submissions']
    assert requested==[('quick_grading','x=2')]
    assert sub['image_ref']==image_ref and sub['transcription_revisions'][0]['steps']==CASES[10]['steps']
    assert other['quick_checks'][0]['id']==before
    assert p.effective(w,sub)['verdict']=='correct' and not p.effective(w,sub)['confirmed']
    assert not w['notebook'][0]['active_error']
