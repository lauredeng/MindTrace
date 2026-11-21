from copy import deepcopy
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from PIL import Image
from core import backup,classroom as c,product as p,presentation as v,learning_records as learning
from core.repository import Repository
from test_persistent_learning import setup_work,assess
from test_backend_api import api,auth


def png():
    buffer=io.BytesIO();Image.new('RGB',(20,20),'white').save(buffer,format='PNG');return buffer.getvalue()


def test_backup_restores_database_and_hashed_evidence_without_overwriting(tmp_path):
    root=tmp_path/'data';root.mkdir()
    repo=Repository(root/'mindtrace.db');w,b,s=setup_work()
    image=png();ref=c.attach_image(image,root/'classroom_images');s['image_ref']=ref
    scope=root/'classroom_v1.json';repo.save(w,str(scope))
    manifest=backup.create(repo,root,tmp_path/'backup')
    assert manifest['status']=='complete'
    restored=backup.restore(tmp_path/'backup',tmp_path/'restored')
    assert restored.load(scope=str(tmp_path/'restored'/'classroom_v1.json'))['id']==w['id']
    assert c.read_image(ref,tmp_path/'restored'/'classroom_images')==image
    with pytest.raises(FileExistsError):backup.restore(tmp_path/'backup',root)
    path=tmp_path/'backup'/'classroom_images'/(ref+'.image');path.write_bytes(b'tampered')
    with pytest.raises(ValueError):backup.restore(tmp_path/'backup',tmp_path/'bad-restore')


def test_independent_worker_process_can_consume_persisted_task(tmp_path):
    repo=Repository(tmp_path/'jobs.db');w,b,s=setup_work();repo.save(w,'scope')
    repo.enqueue_batch(w['id'],b['id'])
    script='''from core.repository import Repository
from core.background import Worker
import sys
repo=Repository(sys.argv[1])
def fixture(*args,**kwargs):
    return dict(verdict='correct',process_checked=False,basis='Explicit offline child-process fixture')
assert Worker(repo,fixture).tick()
'''
    env=dict(os.environ,MINDTRACE_HEADLESS='1')
    result=subprocess.run([sys.executable,'-c',script,str(repo.path)],cwd=Path(__file__).resolve().parents[1],env=env,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert repo.jobs(w['id'],b['id'])[0]['status']=='completed'
    assert repo.load(workspace_id=w['id'])['submissions'][0]['quick_checks'][-1]['verdict']=='correct'


def test_changed_type_invalidates_cached_grades_but_preserves_raw_work():
    w,b,s=setup_work()
    p.quick_check(s,lambda *a,**k:dict(verdict='correct',process_checked=False,basis='离线样例'))
    v.override_grade(w,s['id'],'correct','原题型已核对。')
    s=w['submissions'][0];fingerprint=s['fingerprint']
    v.update_types(w,b['id'],[dict(q,question_type='解答题') for q in b['questions']])
    assert s['fingerprint']==fingerprint
    assert p.effective(w,s)['verdict']=='uncertain'
    assert not p.current_records(s,'quick_checks')
    a,r=assess(w,s)
    assert learning.latest_assessment(w,a)['id']==r['id']


def test_uploaded_student_asset_cannot_be_read_or_claimed_by_peer(api):
    client,t,a,b,w,batch=api
    data=png();ref=hashlib.sha256(data).hexdigest()
    assert client.put('/assets/'+ref,headers=auth(a),content=data).status_code==200
    sub=w['submissions'][0]
    payload=dict(submission_id=sub['id'],expected_fingerprint=sub['fingerprint'],steps=[],answer='',
                 attachment_refs=[ref],command_id='photo-correction')
    assert client.post('/corrections',headers=auth(a),json=payload).status_code==200
    assert client.get('/assets/'+ref,headers=auth(a)).content==data
    assert client.get('/assets/'+ref,headers=auth(t)).status_code==200
    assert client.get('/assets/'+ref,headers=auth(b)).status_code==404
    peer=next(s for s in w['submissions'] if s['student_id']=='002')
    payload.update(submission_id=peer['id'],expected_fingerprint=peer['fingerprint'])
    assert client.post('/corrections',headers=auth(b),json=payload).status_code==422


def test_asset_reservation_budget_is_atomic_and_staged_is_not_readable(tmp_path):
    repo=Repository(tmp_path/'assets.db');w,b,s=setup_work();repo.save(w,'scope')
    repo.stage_asset(w['id'],'a'*64,100,owner='001',budget=100)
    assert not repo.owns_asset(w['id'],'a'*64,'001')
    with pytest.raises(ValueError):repo.stage_asset(w['id'],'b'*64,1,owner='001',budget=100)
    repo.ready_asset(w['id'],'a'*64)
    assert repo.owns_asset(w['id'],'a'*64,'001')
    assert not repo.owns_asset(w['id'],'a'*64,'002')
