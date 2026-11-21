"""Two actual browser sessions against app:8564 and independent API:8570.
All seeded work is explicitly constructed. The worker portion uses confirmed
objective references, so no model call or API key is required.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
import httpx
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core import product as product,presentation as presentation
OUT=ROOT/'artifacts'/'cross-browser';OUT.mkdir(parents=True,exist_ok=True)
API='http://127.0.0.1:8570'


def call(method,path,code=None,data=None):
    response=httpx.request(method,API+path,headers={'Authorization':'Bearer '+code} if code else {},json=data,timeout=30,trust_env=False)
    response.raise_for_status();return response.json()


def local_only(route):
    if urlparse(route.request.url).hostname in (None,'127.0.0.1','localhost'):route.continue_()
    else:route.abort()


def connect(page,code):
    page.goto('http://127.0.0.1:8564',wait_until='networkidle')
    page.get_by_text('课堂连接',exact=True).click()
    page.get_by_role('textbox',name='课堂访问码',exact=True).fill(code)
    page.get_by_role('button',name='连接课堂',exact=True).click()
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)


def main():
    checks=[]
    teacher=call('POST','/classrooms',data={'name':'自动化联调构造课堂'})['code']
    base=call('GET','/workspace',teacher);w=deepcopy(base)
    rows=[dict(student_id=sid,question='已知 $f(x)=x^3-3x$，若直线 $y=m$ 与函数图像有三个不同交点，求 $m$ 的取值范围。',
               question_no='19',question_type='解答题',topic='函数与导数',steps=["f'(x)=3x²-3",'极大值为2，极小值为-2'],answer='[-2,2]') for sid in ('001','002')]
    batch=product.create_batch(w,'导数周练 · 构造联调',rows,'constructed_examples',grading_policy=product.CLASSROOM_POLICY)
    for sid in batch['submission_ids']:presentation.override_grade(w,sid,'incorrect','端点需要进一步核对。')
    call('POST','/workspace/sync',teacher,{'base':base,'after':w})
    student=call('POST','/students/invite',teacher,{'student_id':'001'})['code']
    peer=call('POST','/students/invite',teacher,{'student_id':'002'})['code']
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        teacher_context=browser.new_context(viewport={'width':1440,'height':1100});teacher_context.route('**/*',local_only)
        student_context=browser.new_context(viewport={'width':1440,'height':1100});student_context.route('**/*',local_only)
        t=teacher_context.new_page();s=student_context.new_page()
        connect(t,teacher);connect(s,student)
        s.get_by_role('button',name='订正与复习',exact=True).click()
        expect(s.get_by_role('heading',name='订正与复习',exact=True)).to_be_visible(timeout=30000)
        s.get_by_role('textbox',name='本次解题过程',exact=True).fill('结合三个单调区间及极值，排除端点时才有三个不同交点。')
        s.get_by_role('textbox',name='本次最终答案',exact=True).fill('-2<m<2')
        s.get_by_role('button',name='提交作答',exact=True).click()
        # The teacher sees a newly appended attempt from a separate session/API.
        t.get_by_role('tab',name='学生反馈',exact=True).click()
        expect(t.get_by_role('textbox',name='反馈与依据',exact=True)).to_be_visible(timeout=30000)
        s.get_by_role('textbox',name='本次解题过程',exact=True).fill('尚未提交的订正草稿')
        t.get_by_text('正确',exact=True).last.click()
        t.get_by_role('textbox',name='反馈与依据',exact=True).fill('独立浏览器联调：端点已排除，订正正确。')
        t.get_by_role('button',name='保存订正反馈',exact=True).click()
        expect(t.get_by_text('教师反馈：独立浏览器联调：端点已排除，订正正确。',exact=True)).to_be_visible(timeout=15000)
        # Wait for the real classroom-sync fragment, then check unsent form input.
        s.wait_for_timeout(4500)
        assert s.get_by_role('textbox',name='本次解题过程',exact=True).input_value()=='尚未提交的订正草稿','Background synchronization lost the draft'
        s.get_by_role('tab',name='作答记录',exact=True).click()
        expect(s.get_by_text('教师反馈：独立浏览器联调：端点已排除，订正正确。',exact=True)).to_be_visible(timeout=15000)
        t.screenshot(path=str(OUT/'teacher-feedback.png'));s.screenshot(path=str(OUT/'student-feedback.png'))
        checks.extend(['Separate teacher/student browser sessions exchange correction and feedback through the API',
                       'Unsubmitted student form survives the classroom refresh'])
        peer_view=call('GET','/workspace',peer)
        assert not peer_view['correction_attempts']
        checks.append('Peer cannot see the correction or feedback of student 001')
        teacher_context.close();student_context.close();browser.close()
    # Queue objective work, then process it in independent worker processes after
    # both UI sessions are closed. Each process exits; the next resumes the DB.
    base=call('GET','/workspace',teacher);w=deepcopy(base)
    local=product.create_batch(w,'后台恢复 · 本地参考比对',[
        dict(student_id=sid,question='选择所有正确选项：A 正确，B 错误，C 正确。',question_no='9',question_type='多选题',answer=answer)
        for sid,answer in [('001','AC'),('002','A')]],'constructed_examples',grading_policy=product.CLASSROOM_POLICY)
    groups,_=product.reference_catalog(w,local)
    product.save_references(w,local['id'],{key:('AC','按完整选项集合判定。') for key in groups},product.digest(local.get('answer_keys',{})))
    call('POST','/workspace/sync',teacher,{'base':base,'after':w})
    assert call('POST','/assignments/'+local['id']+'/grade',teacher)['queued']==2
    env=dict(os.environ,MINDTRACE_HEADLESS='1',MINDTRACE_DATABASE=str(ROOT/'artifacts'/'live-integration'/'mindtrace.db'),
             MINDTRACE_CLASSROOM_DIR=str(ROOT/'artifacts'/'live-integration'/'classrooms'))
    for _ in range(2):
        process=subprocess.run([sys.executable,'scripts/run_worker.py','--once'],cwd=ROOT,env=env,capture_output=True,timeout=30)
        assert process.returncode==0,process.stderr.decode(errors='replace')
    jobs=call('GET','/assignments/'+local['id']+'/jobs',teacher)
    assert all(job['status']=='completed' for job in jobs)
    checks.append('After browser closure, separate restarted worker processes complete the persisted queue using local references')
    (OUT/'result.json').write_text(json.dumps({'status':'passed','checks':checks,
        'scope':'Explicit constructed inputs; no real OCR or paid model requests.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=True))


if __name__=='__main__':main()
