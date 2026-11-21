"""Real browser + official service + classroom teacher review + official FSRS, no LLM."""
import json
import re
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_tutor_fixture import prepare
from core import collaboration as collab,learning_records as learning,tutor_learning
import httpx
from playwright.sync_api import sync_playwright,expect

out=ROOT/'artifacts'/'deeptutor';fixture=prepare();api='http://127.0.0.1:8591';web='http://127.0.0.1:8592'
with httpx.Client(base_url=api,trust_env=False,timeout=30) as client:
    r=client.post('/api/mindtrace/tickets',headers={'Authorization':'Bearer '+fixture['student_code']},json={})
    r.raise_for_status();ticket=r.json()['ticket']
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1100});page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(web+'/mindtrace#ticket='+ticket,wait_until='domcontentloaded',timeout=120000)
    expect(page.get_by_role('navigation',name='学习内容')).to_be_visible(timeout=60000)
    page.screenshot(path=str(out/'learning-dashboard.png'),full_page=True)
    add=page.get_by_role('button',name=re.compile('^加入复习 '))
    if add.count() and add.first.is_enabled():add.first.click();expect(page.get_by_role('status')).to_contain_text('已加入复习计划')
    page.get_by_role('button',name='学习证据',exact=True).click()
    expect(page.get_by_text('理解有迹可循，进步有据可查。',exact=True)).to_be_visible()
    page.screenshot(path=str(out/'learning-evidence.png'),full_page=True)
    page.get_by_role('button',name='复习计划',exact=True).click()
    expect(page.get_by_role('button',name='独立重做',exact=True).first).to_be_visible()
    page.get_by_role('button',name='独立重做',exact=True).first.click()
    dialog=page.get_by_role('dialog',name='独立重做')
    expect(dialog).to_be_visible()
    # Independent screen contains the problem, never the teacher's solution.
    expect(dialog.get_by_text('正确导数为1/x-a',exact=False)).to_have_count(0)
    dialog.get_by_role('textbox',name='复习解题过程').fill("f'(x)=1/x-a。由a>0知1/a>0，函数先增后减。")
    dialog.get_by_role('textbox',name='复习最终答案').fill('最大值为-ln(a)-1。')
    with page.expect_response(lambda r:'/review-runs/' in r.url and r.url.split('?')[0].endswith('/attempt')) as submission:
        dialog.get_by_role('button',name='提交作答',exact=True).click()
    result=submission.value.json();assert result['independent'] and not result['can_rate']
    expect(dialog.get_by_text('作答已保存，等待教师复核',exact=True)).to_be_visible()
    page.screenshot(path=str(out/'independent-review.png'),full_page=False)
    # Actual teacher domain command on this explicit synthetic classroom.
    binding={'class_id':collab.resolve(fixture['teacher_code'])['class_id'],'student_id':'DEMO-001'}
    tutor_learning.mutate(binding,lambda w:learning.assess_correction(w,result['attempt_id'],'correct',
        '匿名验证：教师已核对导数、定义域和全局最大值。',command_id='browser-teacher-'+result['attempt_id']))
    dialog.get_by_role('button',name='刷新核验结果',exact=True).click()
    expect(dialog.get_by_text('本次核验通过',exact=True)).to_be_visible()
    dialog.get_by_role('button',name='顺利完成',exact=True).click()
    expect(page.get_by_role('status')).to_contain_text('复习已记录，下次复习')
    w=tutor_learning.workspace(binding);event=next(e for e in w['review_events'] if e['attempt_id']==result['attempt_id'])
    assert event['rating']==3 and event['scheduler_version'].startswith('fsrs-6.3.3')
    # Server-observed source exposure overrides an unchecked self-report.
    page.get_by_role('button',name='独立重做',exact=True).first.click()
    expect(dialog).to_be_visible()
    exposure=page.request.get(web+'/api/mindtrace/source/'+fixture['submission_id'])
    assert exposure.status==200
    dialog.get_by_role('textbox',name='复习最终答案').fill('最大值为-ln(a)-1。')
    with page.expect_response(lambda r:'/review-runs/' in r.url and r.url.split('?')[0].endswith('/attempt')) as assisted:
        dialog.get_by_role('button',name='提交作答',exact=True).click()
    assert not assisted.value.json()['independent']
    dialog.get_by_role('button',name='关闭复习',exact=True).click()
    page.get_by_role('button',name='我的错题',exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('article').first).to_be_visible()
    page.locator('article').first.scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    page.screenshot(path=str(out/'learning-mobile.png'),full_page=False)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    assert not errors,errors
    context.close();browser.close()
checks=['dashboard','scoped_evidence','answer_hidden','teacher_review_refresh','official_fsrs_saved',
        'observed_help_not_independent','mobile_no_horizontal_overflow','no_browser_runtime_error']
(out/'learning-loop-results.json').write_text(json.dumps({'checks':checks,'model_calls':0},indent=2),encoding='utf-8')
print(json.dumps({'passed':len(checks),'model_calls':0}))
