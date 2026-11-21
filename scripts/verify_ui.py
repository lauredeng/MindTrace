"""Offline browser acceptance against running local app/explicit UI fixture.
Start app.py on 8561 and tests/ui_fixture.py on 8562 before running this file.
No credentials or paid model calls. Outputs go to ignored artifacts/phase01/.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts'/'phase01'
OUT.mkdir(parents=True,exist_ok=True)
APP_URL=os.getenv('MINDTRACE_PREVIEW_URL','http://127.0.0.1:8561')
FIXTURE_URL=os.getenv('MINDTRACE_REVIEW_FIXTURE_URL','http://127.0.0.1:8562')


def check_page(page):
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    overflow=page.evaluate('''() => {
      const main=document.querySelector('[data-testid="stMain"]');
      return {body:document.documentElement.scrollWidth>innerWidth+2,
              main:main ? main.scrollWidth>main.clientWidth+2:false};
    }''')
    assert not any(overflow.values()),overflow


def local_only(route):
    host=urlparse(route.request.url).hostname
    if host is None or host in ('127.0.0.1','localhost'):
        route.continue_()
    else:
        route.abort()


checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(device_scale_factor=1)
    context.route('**/*',local_only)
    for width,height in [(1440,1050),(1280,1000),(768,1000),(390,844)]:
        page=context.new_page()
        page.set_viewport_size({'width':width,'height':height})
        page.goto(APP_URL,wait_until='networkidle')
        expect(page.locator('.landing-classic')).to_be_visible(timeout=30000)
        student=page.locator('.st-key-v11_surface_home_student')
        if width>700:
            before=student.evaluate('(el)=>getComputedStyle(el).backgroundImage')
            student.hover()
            page.wait_for_timeout(600)
            after=student.evaluate('(el)=>getComputedStyle(el).backgroundImage')
            assert before!=after,(width,before,after)
            assert 'matrix' in student.evaluate('(el)=>getComputedStyle(el).transform')
            page.mouse.move(1,1)
            page.wait_for_timeout(600)
        check_page(page)
        page.screenshot(path=str(OUT/f'home-{width}.png'),full_page=True)
        checks.append(f'home width {width}: renders, no horizontal overflow')
        if width==1440:
            student.get_by_role('button',name=re.compile('^学生学习空间')).focus()
            assert student.evaluate('(el)=>el.matches(":focus-within")')
            page.screenshot(path=str(OUT/'home-keyboard-focus.png'))
            student.get_by_role('button',name=re.compile('^学生学习空间')).click()
            expect(page.get_by_role('heading',name='AI解题与辅导',exact=True)).to_be_visible(timeout=30000)
            check_page(page)
            page.screenshot(path=str(OUT/'student-entry.png'),full_page=True)
            checks.append('student card enters directly; real student entry renders')
        page.close()

    reduced=context.new_page()
    reduced.set_viewport_size({'width':1440,'height':1000})
    reduced.emulate_media(reduced_motion='reduce')
    reduced.goto(APP_URL,wait_until='networkidle')
    card=reduced.locator('.st-key-v11_surface_home_student')
    card.hover()
    assert card.evaluate('(el)=>getComputedStyle(el).transform')=='none'
    checks.append('reduced motion disables card transforms')
    reduced.close()

    teacher=context.new_page()
    teacher.set_viewport_size({'width':1440,'height':1100})
    teacher.goto(FIXTURE_URL,wait_until='networkidle')
    expect(teacher.locator('.review-case-header')).to_contain_text('1001',timeout=30000)
    check_page(teacher)
    teacher.locator('.review-case-header').evaluate('(el)=>el.scrollIntoView({block:"start"})')
    teacher.screenshot(path=str(OUT/'teacher-review-desktop.png'))
    teacher.get_by_role('button',name='下一份 →',exact=True).click()
    expect(teacher.locator('.review-case-header')).to_contain_text('1002')
    teacher.get_by_role('button',name='← 上一份',exact=True).click()
    expect(teacher.locator('.review-case-header')).to_contain_text('1001')
    teacher.get_by_role('button',name='教师改判',exact=False).click()
    teacher.get_by_role('combobox',name='批改结论',exact=True).click()
    teacher.get_by_role('option',name='正确',exact=True).click()
    teacher.get_by_role('textbox',name='教师备注 / 修改依据',exact=True).fill('界面验收：检查复核更新与统计联动。')
    teacher.get_by_role('button',name='保存复核并更新统计',exact=True).click()
    expect(teacher.locator('.review-case-header')).to_contain_text('1001')
    expect(teacher.get_by_text('界面验收：检查复核更新与统计联动。',exact=True)).to_be_visible()
    check_page(teacher)
    checks.append('teacher previous/next navigation and persisted session override work')
    teacher.locator('[data-testid="stMain"]').evaluate('(el)=>el.scrollTo(0,0)')
    teacher.get_by_text('学生错题本',exact=True).click()
    expect(teacher.get_by_role('heading',name='我的错题本',exact=True)).to_be_visible()
    check_page(teacher)
    teacher.screenshot(path=str(OUT/'notebook-after-review.png'))
    checks.append('same fixture workspace: teacher override is visible to student notebook')
    teacher.close()
    for width in (768,390):
        page=context.new_page()
        page.set_viewport_size({'width':width,'height':1050})
        page.goto(FIXTURE_URL,wait_until='networkidle')
        expect(page.locator('.review-case-header')).to_be_visible(timeout=30000)
        page.locator('.review-case-header').evaluate('(el)=>el.scrollIntoView({block:"start"})')
        check_page(page)
        page.screenshot(path=str(OUT/f'teacher-review-{width}.png'))
        checks.append(f'teacher width {width}: no exception/overflow')
        page.close()
    context.close()
    browser.close()

(OUT/'browser-results.json').write_text(json.dumps({'status':'passed','checks':checks,
    'evidence_scope':'Offline UI fixture; no real OCR, model grading or cross-browser classroom persistence measured.'},
    ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','checks':checks},ensure_ascii=True,indent=2))
