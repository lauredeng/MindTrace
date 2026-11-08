"""Real Chrome screenshots of stored actual API responses. No API actions clicked."""
import json,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/v12-design';OUT.mkdir(exist_ok=True)
report={'actual_api_responses_from':'artifacts/v12-live','materials':'constructed, not human learning outcomes',
    'page_errors':[],'new_model_calls':False,'checks':[]}
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=b.new_page(viewport={'width':1600,'height':1200})
    page.on('pageerror',lambda err:report['page_errors'].append(str(err)))
    def idle():
        page.wait_for_timeout(650)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=60000)
        page.wait_for_timeout(300)
        assert page.locator('[data-testid=stException]').count()==0
    def shot(name):
        idle();page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
    def click(name):page.get_by_role('button',name=name,exact=True).click();idle()
    def nav(name):page.locator('[data-testid=stSidebar]').get_by_text(name,exact=True).click();idle()
    page.goto('http://127.0.0.1:8505',wait_until='networkidle')
    page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    shot('01-home');click('进入教师工作台');shot('02-grading')
    nav('班级学情')
    page.get_by_text('查看全部批次的最近作答',exact=True).click();idle()
    shot('03-class-insights')
    assert page.get_by_label('选择相似错误类别',exact=True).count()==1
    page.get_by_text('相似错误与跨题重复',exact=True).scroll_into_view_if_needed()
    shot('04-common-error-evidence')
    nav('历史记录');shot('05-history')
    click('返回产品首页');click('进入学生学习中心');shot('06-student-solve')
    nav('我的错题本');shot('07-notebook')
    nav('错因分析');shot('08-causes')
    click('返回产品首页');click('进入学生学习中心')
    field=page.get_by_role('combobox',name='匿名学习编号',exact=True)
    field.fill('V12-SELF');field.press('ArrowDown')
    page.get_by_text('V12-SELF',exact=True).last.click();idle()
    shot('09-unanswered-solution')
    page.get_by_text('这次在解决：回答学生的新问题',exact=False).count()
    report['checks'].append('Actual-response teacher, class, evidence, history, notebook, causes and no-answer solution pages render')
    mobile=b.new_page(viewport={'width':390,'height':844})
    mobile.goto('http://127.0.0.1:8505')
    mobile.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    mobile.get_by_role('button',name='进入教师工作台',exact=True).click()
    mobile.get_by_role('button',name='开始批改并分析错题',exact=True).wait_for(timeout=30000)
    mobile.wait_for_timeout(800)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    mobile.screenshot(path=str(OUT/'10-mobile-grading.png'),full_page=True)
    report['checks'].append('390px teacher page renders without document overflow')
    b.close()
with urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=15) as response:report['main_health']=response.status
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

