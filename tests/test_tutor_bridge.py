"""Actual classroom ownership and durable one-time handoff, no model calls."""
from copy import deepcopy
import json
import pytest
from core import classroom as c,collaboration as x,product as p,tutor_bridge as t


@pytest.fixture
def bridge_case(tmp_path):
    teacher=x.create('辅导接入离线验证')
    access=x.resolve(teacher);w=x.load(teacher)
    p.create_batch(w,'同一次数学作业',[
        {'student_id':sid,'question_no':'1','question':'求导 log(x)-2*x','answer':answer,'steps':[answer],
         'topic':'函数与导数','question_type':'解答题'} for sid,answer in [('001','1/x'),('002','1/x-2')]])
    for s in w['submissions']:p.sync_notebook(w,s['id'],manual=True)
    c.save(w,x._folder(access['class_id'])/'workspace.json')
    codes=[x.invite(teacher,sid) for sid in ('001','002')]
    store=t.BridgeStore(tmp_path/'bridge.sqlite3')
    return store,teacher,codes,w


def login(store,code,sid=None):
    token=store.ticket(code,sid);principal,cookie=store.exchange(token)
    return principal,cookie


def test_one_time_ticket_has_no_plaintext_classroom_credential(bridge_case):
    store,teacher,codes,w=bridge_case
    token=store.ticket(codes[0],w['submissions'][0]['id'])
    principal,cookie=store.exchange(token)
    assert store.principal(cookie)['student_id']=='001'
    with pytest.raises(ValueError):store.exchange(token)
    data=store.path.read_bytes()
    assert codes[0].encode() not in data and cookie.encode() not in data and token.encode() not in data


def test_teacher_and_foreign_student_cannot_open_personal_lesson(bridge_case):
    store,teacher,codes,w=bridge_case
    with pytest.raises(ValueError):store.ticket(teacher)
    with pytest.raises(ValueError):store.ticket(codes[0],w['submissions'][1]['id'])
    principal,cookie=login(store,codes[0])
    assert len(t.student_records(principal))==1
    with pytest.raises(ValueError):t.source(principal,w['submissions'][1]['id'])


def test_revocation_invalidates_browser_grant_not_only_next_login(bridge_case):
    store,teacher,codes,w=bridge_case
    principal,cookie=login(store,codes[0]);access=x.resolve(teacher)
    path=x._folder(access['class_id'])/'access.json';meta=json.loads(path.read_text(encoding='utf-8'))
    del meta['students']['001'];x._write_meta(path.parent,meta)
    with pytest.raises(ValueError):store.principal(cookie)


def test_source_version_changes_and_never_exports_whole_sheet(bridge_case):
    store,teacher,codes,w=bridge_case
    principal,cookie=login(store,codes[0]);sid=w['submissions'][0]['id']
    before=t.source(principal,sid)
    w['submissions'][0]['transcription']='secret-other-student-entire-sheet'
    w['submissions'][0]['image_ref']='a'*64
    w['submissions'][0]['reference_revision']='teacher-revised-reference'
    c.save(w,x._folder(x.resolve(teacher)['class_id'])/'workspace.json')
    after=t.source(principal,sid)
    assert before['source_revision']!=after['source_revision']
    assert 'secret-other-student' not in t.context_text(after) and 'image_ref' not in after


def test_native_session_mapping_is_durable_and_scoped(bridge_case):
    store,teacher,codes,w=bridge_case
    a,_=login(store,codes[0]);b,_=login(store,codes[1]);sid=w['submissions'][0]['id']
    row=dict(principal_id=a['id'],submission_id=sid,revision='r1',session_id='native-session',
             notebook_id='native-notebook',record_id='native-record',path_id='native-path')
    store.put_lesson(row)
    reloaded=t.BridgeStore(store.path)
    assert reloaded.lesson(a['id'],sid,'r1')==row
    assert reloaded.by_session(b['id'],'native-session') is None
    assert reloaded.lesson(a['id'],sid,'r2') is None
