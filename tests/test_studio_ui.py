from navigation_helpers import route,main_labels
"""UI loop with an explicit offline transport fixture, not live AI evidence."""
import json
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from core import ai,education as e
from test_education import report,exercise,grade,tutor

ROOT=Path(__file__).resolve().parents[1]

def click(at,label):
    next(b for b in at.button if b.label==label).click().run()
    assert not at.exception

@pytest.fixture
def studio(monkeypatch):
    monkeypatch.setenv('MINDTRACE_ENV','production')
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE','0')
    monkeypatch.setattr(ai,'ai_ready',lambda:True)
    calls=[]
    def offline(messages,**kwargs):
        purpose=kwargs['purpose'];calls.append(purpose)
        if purpose=='diagnosis':
            raw=json.loads(messages[1]['content'])
            sub=e.normalize_submission(dict(raw,student_id='fixture'))
            return report(sub,2)
        if purpose=='tutoring':
            return tutor()
        if purpose=='exercise':
            return exercise()
        if purpose=='grading':
            return grade()
        return 'offline class advice'
    monkeypatch.setattr(ai,'completion',offline)
    at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not at.exception
    return at,calls

def test_default_general_home_and_complete_teacher_student_loop(studio):
    at,calls=studio
    assert at.session_state['experience_page']=='产品首页'
    click(at,'进入教师工作台')
    assert at.session_state['experience_page']=='作业批改'
    route(at,'作业分析')
    click(at,'载入跨章节匿名材料')
    assert calls==[]
    select=next(s for s in at.selectbox if s.label=='选择题目 · 原文与分析联动')
    select.select_index(10).run()
    click(at,'分析 / 重新分析当前题')
    assert calls==['diagnosis']
    # Refresh reuses records and never runs a new model call.
    at.run()
    assert calls==['diagnosis']
    click(at,'保存复核并更新统计')
    click(at,'分配给该学生')
    w=at.session_state['studio_workspace']
    assert len(w['tasks'])==1 and len(w['reviews'])==1
    click(at,'学生')
    route(at,'专项练习')
    assert not at.exception
    next(s for s in at.selectbox if s.label=='我的匿名学习编号').select_index(0).run()
    click(at,'开始这次学习')
    assert at.session_state['studio_workspace']['tasks'][0]['status']=='in_progress'
    click(at,'先问我一个诊断问题')
    assert calls[-1]=='tutoring'
    click(at,'直接生成针对性独立练习')
    next(t for t in at.text_area if t.label=='本次练习答案').set_value('x=1')
    next(t for t in at.text_area if t.label=='本次练习过程 · 每行一步').set_value('-2*x+8=6\n-2*x=-2\nx=1')
    click(at,'提交并验证这次作答')
    w=at.session_state['studio_workspace']
    assert len(w['attempts'])==1 and w['attempts'][0]['independently_verified']
    click(at,'结束本次学习并反馈任务结果')
    assert at.session_state['studio_workspace']['tasks'][0]['status']=='completed'
    click(at,'教师')
    route(at,'教学任务')
    assert not at.exception
    assert any('当前迁移验证' in str(d.value) for d in at.dataframe)
    click(at,'学生')
    route(at,'学习档案')
    assert not at.exception
    assert at.metric[2].value=='1'

def test_new_workspace_isolated_and_no_key_ui(studio):
    at,calls=studio
    assert not any('Key' in t.label for t in at.text_input)
    click(at,'进入教师工作台')
    route(at,'工作台首页')
    click(at,'体验匿名示例')
    second=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not second.exception
    assert not second.metric
    assert second.session_state['studio_workspace']['submissions']==[]
    assert calls==[]



def test_role_navigation_and_empty_guidance_without_calls(studio):
    at,calls=studio
    assert not at.metric
    click(at,'进入学生学习中心')
    assert at.session_state['experience_page']=='AI解题与辅导'
    click(at,'返回产品首页')
    click(at,'进入教师工作台')
    assert at.session_state['experience_page']=='作业批改'
    route(at,'班级学情')
    assert not at.exception
    click(at,'上传并批改作业')
    assert at.session_state['experience_page']=='作业批改'
    assert calls==[]


def test_insight_drilldown_uses_existing_submission(studio):
    from core import classroom as c
    at,calls=studio
    rows=json.loads((ROOT/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
    w=at.session_state['studio_workspace']
    sub=e.normalize_submission(rows[10]);w['submissions'].append(sub)
    e.analyze_submission(sub,lambda *a,**kw:report(sub,2))
    c.review(w,sub['id'],'confirm','分配律遗漏',['分配律'],'先复核原文','test-review',first_error_step=2)
    click(at,'进入教师工作台')
    route(at,'旧版班级学情')
    assert not at.exception
    assert next(s for s in at.selectbox if s.label=='对应学生与题目').value==sub['id']
    click(at,'复核这道题 / 安排任务')
    assert at.session_state['experience_page']=='作业分析'
    assert at.session_state['studio_selected_question']==sub['id']
    assert at.tabs[0].label=='02 分析与证据复核'
    assert calls==[]
