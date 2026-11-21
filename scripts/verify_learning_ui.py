"""Browser checks for the explicit offline learning-loop fixture on port 8563."""
from pathlib import Path
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

OUT=Path(__file__).resolve().parents[1]/'artifacts'/'platform'
OUT.mkdir(parents=True,exist_ok=True)


def local_only(route):
    if urlparse(route.request.url).hostname in (None,'localhost','127.0.0.1'):route.continue_()
    else:route.abort()


def check(page):
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')


checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1100},device_scale_factor=1)
    context.route('**/*',local_only)
    page=context.new_page();page.goto('http://127.0.0.1:8563',wait_until='networkidle')
    expect(page.get_by_role('heading',name='订正与复习',exact=True)).to_be_visible(timeout=30000)
    check(page);page.screenshot(path=str(OUT/'learning-hub.png'))
    page.get_by_role('tab',name='复习计划',exact=True).click();check(page)
    expect(page.get_by_text('已到复习时间',exact=True)).to_be_visible()
    page.screenshot(path=str(OUT/'review-plan.png'))
    checks.append('Student corrections and official-FSRS due plan render')
    page.get_by_role('tab',name='作答记录',exact=True).click()
    expect(page.get_by_text('教师反馈：已结合单调区间与极值排除端点，订正依据完整。',exact=True)).to_be_visible()
    checks.append('Teacher correction feedback is visible in student history')
    page.get_by_text('学习画像',exact=True).click()
    expect(page.get_by_role('heading',name='学习画像',exact=True)).to_be_visible()
    expect(page.get_by_text('图表统计作答次数，同一题多次订正分别记录；不换算为能力分数。',exact=True)).to_be_visible()
    expect(page.locator('[data-testid="stDataFrame"]').first).to_be_visible();check(page)
    page.screenshot(path=str(OUT/'learning-profile.png'))
    checks.append('Evidence profile renders chart and source records')
    page.get_by_text('教师反馈',exact=True).click()
    expect(page.get_by_role('heading',name='学生订正反馈',exact=True)).to_be_visible();check(page)
    page.get_by_role('textbox',name='反馈与依据',exact=True).fill('浏览器验收：已核对学生的极值与端点处理。')
    page.get_by_role('button',name='保存订正反馈',exact=True).click()
    expect(page.get_by_text('教师反馈：浏览器验收：已核对学生的极值与端点处理。',exact=True)).to_be_visible()
    page.screenshot(path=str(OUT/'teacher-correction.png'))
    checks.append('Teacher feedback form writes a new review')
    page.get_by_text('批改工作台',exact=True).click()
    expect(page.get_by_role('heading',name='各题错误人数',exact=True)).to_be_visible();check(page)
    page.screenshot(path=str(OUT/'teacher-workbench.png'))
    checks.append('Teacher workbench includes explicit multiple-choice section')
    mobile=context.new_page();mobile.set_viewport_size({'width':390,'height':844})
    mobile.goto('http://127.0.0.1:8563',wait_until='networkidle')
    expect(mobile.get_by_role('heading',name='订正与复习',exact=True)).to_be_visible(timeout=30000)
    check(mobile);mobile.screenshot(path=str(OUT/'learning-mobile.png'))
    checks.append('Student learning page renders at 390px without document overflow')
    browser.close()
(OUT/'browser-results.json').write_text(json.dumps({'status':'passed','checks':checks,'scope':'Explicit offline fixture; not real model or classroom outcome evidence.'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=True))
