"""Real upstream student UI + real classroom persistence; no model requests."""
import json
import os
from pathlib import Path
import sys
import httpx
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_tutor_fixture import prepare

OUT=ROOT/'artifacts'/'deeptutor';fixture=prepare()
API='http://127.0.0.1:8591';WEB='http://127.0.0.1:8592'
checks=[]
with httpx.Client(base_url=API,trust_env=False,timeout=30) as client:
    response=client.post('/api/mindtrace/tickets',headers={'Authorization':'Bearer '+fixture['student_code']},
                         json={'submission_id':fixture['submission_id']})
    response.raise_for_status();ticket=response.json()['ticket']
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1100})
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(WEB+'/mindtrace#ticket='+ticket,wait_until='domcontentloaded',timeout=120000)
    page.wait_for_url('**/learning/mastery/**/sessions/**',timeout=120000)
    expect(page.get_by_role('button',name='原题与订正',exact=True)).to_be_visible(timeout=120000)
    expect(page.get_by_text('Feature locked',exact=True)).to_have_count(0)
    expect(page.get_by_text('功能已锁定',exact=True)).to_have_count(0)
    try:expect(page.locator('textarea').first).to_be_visible(timeout=60000)
    except Exception:
        page.screenshot(path=str(OUT/'runtime-error.png'))
        print('Browser errors:',json.dumps(errors,ensure_ascii=True))
        raise
    expect(page.locator('textarea').first).to_be_enabled(timeout=60000)
    expect(page.get_by_text('已关联你的原题、作答与批改反馈。请在下方提出疑问，或说明希望从哪一步开始。',exact=True)).to_be_visible(timeout=60000)
    page.screenshot(path=str(OUT/'official-learning.png'),full_page=False)
    checks.append('Native DeepTutor teaching screen opens from an owned classroom source')
    page.get_by_role('button',name='原题与订正',exact=True).click()
    dialog=page.get_by_role('dialog',name='原题与订正',exact=True)
    expect(dialog.get_by_text('教师确认的反馈',exact=True)).to_be_visible()
    expect(dialog.get_by_text('正确导数为1/x-a；在(0,1/a)上递增，在(1/a,+∞)上递减；最大值为-ln(a)-1。',exact=True)).to_be_visible()
    page.screenshot(path=str(OUT/'original-correction.png'),full_page=False)
    checks.append('Teacher-confirmed evidence and original student work share the native teaching screen')
    dialog.get_by_role('textbox',name='订正过程',exact=True).fill("f'(x)=1/x-a。\nx<1/a时导数为正，x>1/a时导数为负。\nx=1/a时取得最大值-ln(a)-1。")
    dialog.get_by_role('textbox',name='订正答案',exact=True).fill('最大值为-ln(a)-1。')
    dialog.get_by_role('button',name='提交订正',exact=True).click()
    expect(dialog.get_by_role('status')).to_have_text('订正已回传，教师端可查看。',timeout=30000)
    checks.append('Student correction is saved through the existing classroom domain service')
    with httpx.Client(base_url=API,trust_env=False,timeout=30) as client:
        response=client.post('/api/mindtrace/tickets',headers={'Authorization':'Bearer '+fixture['peer_code']},json={})
        response.raise_for_status()
        client.post('/api/mindtrace/connect',json={'ticket':response.json()['ticket']}).raise_for_status()
        assert client.get('/api/mindtrace/source/'+fixture['submission_id']).status_code==404
    checks.append('Another real student account cannot open this source')
    from core import collaboration as collab
    w=collab.load(fixture['teacher_code'])
    attempt=next(a for a in reversed(w['correction_attempts']) if a['submission_id']==fixture['submission_id'])
    assert attempt['student_id']=='DEMO-001' and attempt['hint_used'] and not attempt['independent']
    original=next(s for s in w['submissions'] if s['id']==fixture['submission_id'])
    assert original['answer']=='无最大值。'
    checks.append('Teacher sees the correction while the original answer remains unchanged')
    assert not errors,errors
    context.close();browser.close()
(OUT/'browser-results.json').write_text(json.dumps({'checks':checks,'model_calls':0},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':len(checks),'model_calls':0}))
