from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from api.app import app
from core import collaboration as collab,product as p,learning_records as learning,classroom as c


@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('MINDTRACE_DATABASE',str(tmp_path/'server.db'))
    monkeypatch.setenv('MINDTRACE_CLASSROOM_DIR',str(tmp_path/'classes'))
    teacher=collab.create('接口隔离课堂')
    before=collab.load(teacher);w=deepcopy(before)
    batch=p.create_batch(w,'作业',[dict(student_id=s,question='多选题：A、B正确，C错误。',question_no='1',question_type='多选题',answer='A') for s in ('001','002')],grading_policy=p.CLASSROOM_POLICY)
    collab.save(teacher,before,w)
    first=collab.invite(teacher,'001');second=collab.invite(teacher,'002')
    with TestClient(app) as client:
        yield client,teacher,first,second,w,batch


def auth(code):return {'Authorization':'Bearer '+code}


def test_scope_and_teacher_commands(api):
    client,t,a,b,w,batch=api
    assert client.get('/workspace').status_code==401
    assert client.get('/workspace',headers=auth(a)).json()['submissions'][0]['student_id']=='001'
    assert len(client.get('/workspace',headers=auth(a)).json()['submissions'])==1
    assert client.post('/assignments/'+batch['id']+'/grade',headers=auth(a)).status_code==403
    assert client.post('/assignments/'+batch['id']+'/grade',headers=auth(t)).json()['queued']==2
    assert client.get('/assets/'+'a'*64,headers=auth(a)).status_code==404


def test_end_to_end_correction_feedback_profile_and_fsrs(api):
    client,t,a,b,w,batch=api;sub=w['submissions'][0]
    payload=dict(submission_id=sub['id'],expected_fingerprint=sub['fingerprint'],steps=[],answer='AB',command_id='attempt-one')
    response=client.post('/corrections',headers=auth(a),json=payload)
    assert response.status_code==200,response.text
    attempt=response.json()
    assert client.post('/corrections',headers=auth(a),json=payload).json()['id']==attempt['id']
    assert client.post('/corrections',headers=auth(b),json=payload).status_code==422
    verdict=dict(verdict='correct',note='选项齐全，核对正确。',command_id='teacher-one')
    assert client.post('/corrections/'+attempt['id']+'/review',headers=auth(a),json=verdict).status_code==403
    assert client.post('/corrections/'+attempt['id']+'/review',headers=auth(t),json=verdict).status_code==200
    profile=client.get('/learning/profile',headers=auth(a)).json()
    assert profile['points'][0]['independent_success']==1
    unit=client.post('/learning/units',headers=auth(a),json={'submission_id':sub['id']}).json()
    record=client.post('/learning/reviews',headers=auth(a),json=dict(unit_id=unit['id'],attempt_id=attempt['id'],rating=3,command_id='review-one'))
    assert record.status_code==200,record.text
    assert 'card_after' in record.json()
    assert not client.get('/workspace',headers=auth(b)).json()['correction_attempts']


def test_student_sync_cannot_forge_teacher_assessment(api):
    client,t,a,b,w,batch=api
    base=client.get('/workspace',headers=auth(a)).json();after=deepcopy(base)
    after['correction_reviews'].append({'id':'fake','student_id':'001','submission_id':after['submissions'][0]['id']})
    assert client.post('/workspace/sync',headers=auth(a),json={'base':base,'after':after}).status_code==409


def test_confirmed_objective_reference_verifies_review_without_teacher_click(api):
    client,t,a,b,w,batch=api
    base=client.get('/workspace',headers=auth(t)).json();updated=deepcopy(base)
    groups,_=p.reference_catalog(updated,updated['batches'][0])
    p.save_references(updated,batch['id'],{key:('AB','按完整选项集合核对。') for key in groups},p.digest({}))
    assert client.post('/workspace/sync',headers=auth(t),json={'base':base,'after':updated}).status_code==200
    sub=client.get('/workspace',headers=auth(a)).json()['submissions'][0]
    payload=dict(submission_id=sub['id'],expected_fingerprint=sub['fingerprint'],
                 expected_reference_revision=sub['reference_revision'],steps=[],answer='BA',origin='review',command_id='independent-review')
    response=client.post('/corrections',headers=auth(a),json=payload)
    assert response.status_code==200,response.text
    view=client.get('/workspace',headers=auth(a)).json()
    assert view['correction_reviews'][-1]['method']=='reference_comparison'
    assert view['correction_reviews'][-1]['verdict']=='correct'
