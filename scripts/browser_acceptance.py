"""Browser acceptance: real Chrome, real local Streamlit, no API simulation."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts'
report = {'checks': [], 'browser_errors': []}


def check(page, name):
    page.wait_for_timeout(700)
    errors = page.locator('[data-testid="stException"]')
    assert errors.count() == 0, errors.all_text_contents()
    report['checks'].append(name)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                headless=True, args=['--disable-gpu'])
    page = browser.new_page(viewport={'width': 1512, 'height': 1700}, device_scale_factor=1)
    page.on('pageerror', lambda error: report['browser_errors'].append(str(error)))
    page.goto('http://127.0.0.1:8501', wait_until='networkidle')
    page.get_by_role('heading', name='看见班级共性，照顾每个不同。').wait_for(timeout=60000)
    page.get_by_role('button', name='载入 12 份匿名示例作业').wait_for(timeout=30000)
    page.locator('.footer').wait_for(timeout=30000)
    page.wait_for_timeout(1000)
    assert page.get_by_label('开发者 DeepSeek API Key', exact=True).count() == 0
    assert page.get_by_label('你的 DeepSeek API Key', exact=True).count() == 0
    page.screenshot(path=str(OUT / 'home-desktop.png'), full_page=True)
    check(page, 'Teacher homepage renders')
    page.get_by_role('button', name='载入 12 份匿名示例作业').click()
    page.get_by_text('当前展示人工构造样例；数学验证为本机实时计算。').wait_for(timeout=30000)
    page.get_by_role('button', name='重试保存批次').wait_for(timeout=30000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / 'teacher-results.png'), full_page=True)
    check(page, 'Real sample batch analysis')
    page.get_by_text('证据复核与统计', exact=True).first.click()
    page.get_by_role('heading', name='逐份证据复核').wait_for(timeout=30000)
    page.get_by_role('button', name='保存教师复核').click()
    page.get_by_text('复核意见已保存。').wait_for(timeout=15000)
    page.screenshot(path=str(OUT / 'evidence-review.png'), full_page=True)
    check(page, 'Teacher review persists')
    page.get_by_text('学生辅导体验', exact=True).first.click()
    page.get_by_role('button', name='建立诊断与追问').wait_for(timeout=30000)
    # Live browser acceptance never spends the owner's API quota. Full student
    # dialogue is exercised offline with an isolated transport in AppTest.
    check(page, 'Student workspace renders without requiring a personal key')
    page.get_by_role('tab', name='变式训练').click()
    page.get_by_role('button', name='生成一道新变式').click()
    page.get_by_role('button', name='提交并验证').wait_for(timeout=15000)
    check(page, 'Adaptive practice generates')
    page.get_by_text('学习认知画像', exact=True).first.click()
    page.get_by_role('heading', name='用持续的证据，记录学习变化。').wait_for(timeout=15000)
    check(page, 'Learning profile renders')
    page.get_by_text('运行记录', exact=True).first.click()
    page.get_by_role('heading', name='每次分析，都留下一条可追溯记录。').wait_for(timeout=15000)
    check(page, 'History renders')
    page.get_by_text('导入以前导出的批次 JSON', exact=True).click()
    archive = {'results': [{'student_id': 'Imported-01', 'question': 'x**2', 'student_answer': '2*x'}]}
    page.locator('input[type=file]').set_input_files({
        'name': 'acceptance-batch.json', 'mimeType': 'application/json',
        'buffer': json.dumps(archive).encode('utf-8'),
    })
    page.get_by_role('button', name='导入并重新验证批次').wait_for(timeout=15000)
    page.get_by_role('button', name='导入并重新验证批次').click()
    page.get_by_text('已导入当前工作区，数学结果已重新验证。').wait_for(timeout=15000)
    check(page, 'Downloaded batch JSON can be imported and reverified')
    page.get_by_text('教师批量分析', exact=True).first.click()
    page.get_by_role('heading', name='看见班级共性，照顾每个不同。').wait_for(timeout=15000)
    # Fresh mobile navigation also checks the native responsive sidebar state.
    mobile = browser.new_page(viewport={'width': 390, 'height': 844})
    mobile.goto('http://127.0.0.1:8501')
    mobile.get_by_role('button', name='载入 12 份匿名示例作业').wait_for(timeout=30000)
    mobile.locator('.footer').wait_for(timeout=30000)
    mobile.wait_for_timeout(1000)
    assert mobile.locator('[data-testid="stSidebar"]').get_attribute('data-collapsed') == 'true'
    mobile.screenshot(path=str(OUT / 'home-mobile.png'), full_page=True)
    overflow = mobile.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    assert not overflow
    report['mobile_document_overflow'] = overflow
    check(mobile, 'Mobile layout renders with collapsed navigation')
    browser.close()

(OUT / 'browser-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))

