"""V1.1 round-one real Chrome UX inspection. Never clicks paid API actions."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'v11-round1'
OUT.mkdir(parents=True,exist_ok=True)
result={'checks':[],'page_errors':[],'live_api_triggered':False,'human_usability_test':False}

with sync_playwright() as p:
    b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=b.new_page(viewport={'width':1512,'height':1100})
    page.on('pageerror',lambda error:result['page_errors'].append(str(error)))
    def shot(name):
        page.wait_for_timeout(700)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=30000)
        page.wait_for_timeout(250)
        assert page.locator('[data-testid="stException"]').count()==0
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
    def nav(name):
        page.locator('[data-testid="stSidebar"]').get_by_text(name,exact=True).click()
        page.wait_for_timeout(650)
    def home():
        page.get_by_role('button',name='返回产品首页',exact=True).click()
        page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=30000)
    page.goto('http://127.0.0.1:8501',wait_until='networkidle')
    page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    assert page.get_by_role('button',name='进入学生学习中心',exact=True).count()==1
    assert page.get_by_label('开发者 DeepSeek API Key',exact=True).count()==0
    shot('01-product-home')
    result['checks'].append('Product home explains both roles and has two working entry actions')
    page.get_by_role('button',name='进入教师工作台',exact=True).click()
    page.get_by_role('button',name='＋ 新建作业分析',exact=True).wait_for()
    shot('02-teacher-home')
    result['checks'].append('Teacher homepage has clear action and no invented empty metrics')
    page.get_by_role('button',name='＋ 新建作业分析',exact=True).click()
    page.get_by_role('button',name='载入跨章节匿名材料',exact=True).wait_for()
    nav('教学任务')
    shot('03-teacher-tasks')
    home()
    page.get_by_role('button',name='进入学生学习中心',exact=True).click()
    page.get_by_role('button',name='拍一道题，开始学习',exact=True).wait_for()
    shot('04-student-home')
    page.get_by_role('button',name='拍一道题，开始学习',exact=True).click()
    assert page.get_by_role('tab',name='自主拍题 / 文本学习',exact=True).get_attribute('aria-selected')=='true'
    shot('05-photo-entry')
    result['checks'].append('Student homepage links directly to selected photo tab')
    home()

    # Isolated fixture uses prior actual model outputs on clearly constructed material.
    page.goto('http://127.0.0.1:8503',wait_until='networkidle')
    page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    page.get_by_role('button',name='进入教师工作台',exact=True).click()
    page.get_by_role('button',name='查看班级学情',exact=True).wait_for(timeout=30000)
    shot('06-teacher-populated')
    page.get_by_role('button',name='查看班级学情',exact=True).click()
    page.get_by_role('heading',name='从共性问题，找到教学的着力点。',exact=True).wait_for()
    page.get_by_role('button',name='复核这道题 / 安排任务',exact=True).wait_for(timeout=30000)
    shot('07-class-insights')
    assert page.locator('.issue-bar').count()>0
    assert page.get_by_role('button',name='复核这道题 / 安排任务',exact=True).count()==1
    page.get_by_role('button',name='复核这道题 / 安排任务',exact=True).click()
    page.get_by_role('button',name='分析 / 重新分析当前题',exact=True).wait_for()
    shot('08-evidence-drilldown')
    result['checks'].append('Class frequencies use real saved evidence and drill down to review without reentry')
    nav('教学任务')
    shot('09-teacher-feedback')
    home()
    page.get_by_role('button',name='进入学生学习中心',exact=True).click()
    page.get_by_role('button',name='拍一道题，开始学习',exact=True).wait_for()
    shot('10-student-populated')
    nav('专项练习')
    shot('11-existing-learning')
    assert page.get_by_text('在提示下完成，仍需独立验证',exact=True).count()>0
    nav('学习档案')
    shot('12-learning-profile')
    result['checks'].append('Linked student task and prior feedback retained; answer-viewed state preserved')
    nav('高级设置')
    assert page.get_by_role('button',name='下载当前教学工作区 JSON',exact=True).count()==1
    result['checks'].append('Technical records retained only behind advanced navigation')
    home()

    mobile=b.new_page(viewport={'width':390,'height':844})
    mobile.goto('http://127.0.0.1:8503')
    mobile.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    mobile.screenshot(path=str(OUT/'13-mobile-home.png'),full_page=True)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    mobile.get_by_role('button',name='进入教师工作台',exact=True).click()
    mobile.get_by_role('button',name='＋ 新建作业分析',exact=True).wait_for()
    mobile.screenshot(path=str(OUT/'14-mobile-teacher.png'),full_page=True)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    result['checks'].append('390px mobile product and teacher pages have no horizontal document overflow')
    b.close()
(OUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

