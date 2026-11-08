"""App-level tests for scoped classroom connection and visible feedback."""
import json
from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from core import collaboration as x,classroom as c,product as p,ai
from test_product import quick,deep
from test_education import CASES
ROOT=Path(__file__).resolve().parents[1]

def click(at,label):
    next(b for b in at.button if b.label==label).click().run()
    assert not at.exception

def test_two_sessions_load_same_sources_and_refresh_personal_feedback(monkeypatch,tmp_path):
    monkeypatch.setenv('MINDTRACE_ENV','production');monkeypatch.setenv('MINDTRACE_CLASSROOM_DIR',str(tmp_path))
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE','0')
    code=x.create('双浏览器验收');base=x.load(code);w=deepcopy(base)
    b=p.create_batch(w,'同一份教师原题',[dict(CASES[10],student_id=sid) for sid in ('A','B')])
    for row in w['submissions']:
        p.quick_check(row,lambda *a,_s=row,**k:quick(_s));p.deep_analyze(row,lambda *a,_s=row,**k:deep(_s));p.sync_notebook(w,row['id'])
    x.save(code,base,w);student_code=x.invite(code,'A')
    teacher=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(t for t in teacher.text_input if t.label=='课堂访问码').set_value(code);click(teacher,'连接课堂')
    student=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    next(t for t in student.text_input if t.label=='课堂访问码').set_value(student_code);click(student,'连接课堂')
    assert student.session_state['studio_current_student']=='A'
    assert {s['student_id'] for s in student.session_state['studio_workspace']['submissions']}=={'A'}
    assert not any(b.label=='教师' for b in student.sidebar.button)
    student.session_state['experience_destination']=('教师工作空间','作业批改');student.run()
    assert student.session_state['experience_role']=='学生学习空间'
    click(student,'我的错题本');click(student,'查看解析')
    next(s for s in student.selectbox if s.label=='主要错因').set_value('计算失误')
    next(t for t in student.text_area if t.label=='我的备注').set_value('同一课堂里的真实界面修订')
    click(student,'保存错因与个人修订')
    # Saving a teacher edit must receive the merged student feedback immediately;
    # a matching version number alone must never imply a complete local snapshot.
    click(teacher,'保存复核并更新统计')
    assert any('同一课堂里的真实界面修订' in str(t.value) for t in teacher.markdown)
    click(teacher,'刷新课堂数据')
    assert any('同一课堂里的真实界面修订' in str(t.value) for t in teacher.markdown)
    assert x.load(code)['notebook'][0]['notes']=='同一课堂里的真实界面修订'
    click(student,'断开课堂')
    assert student.session_state['collab_guest']
    assert not student.session_state['studio_workspace']['submissions']
