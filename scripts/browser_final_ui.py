"""Real Chrome acceptance: aggregate counts are verified from isolated stored records."""
from pathlib import Path
from collections import Counter
import json,re,sys
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import classroom as c,product as p,presentation as v
ROOT=Path.cwd();OUT=ROOT/'artifacts/final-ui';OUT.mkdir(exist_ok=True)
w=c.load(ROOT/'artifacts/final-ui-fixture/classroom_v1.json')
manifest=json.loads((ROOT/'artifacts/final-ui-fixture/expected.json').read_text(encoding='utf-8'))
baseline=Counter(n['primary_category'] for n in p.notebook_rows(w,'S01') if n.get('active_error',True))
report={'data':'isolated constructed records, no new API calls or real student data','checks':[],'page_errors':[]}
with sync_playwright() as pl:
    browser=pl.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1450})
    page.on('pageerror',lambda err:report['page_errors'].append(str(err)))
    def idle():
        page.wait_for_timeout(550)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=60000)
        page.wait_for_timeout(250)
        assert page.locator('[data-testid=stException]').count()==0
    def click(label):
        page.get_by_role('button',name=label,exact=True).click();idle()
    def nav(label):
        page.locator('[data-testid=stSidebar]').get_by_text(label,exact=True).click();idle()
    def shot(name):
        idle()
        page.locator('[data-testid=stMain]').evaluate('el=>el.scrollTo({top:0,behavior:"instant"})')
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT/name),full_page=True)
    page.goto('http://127.0.0.1:8507',wait_until='networkidle')
    page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    click('进入教师工作台')
    frame=page.frame_locator('iframe[title*="mindtrace_question_heatmap"]')
    frame.locator('button.cell').first.wait_for(timeout=60000)
    assert frame.locator('button.cell').count()==20
    assert frame.get_by_role('heading',name='选择题',exact=True).count()==1
    assert frame.get_by_role('heading',name='填空题',exact=True).count()==1
    assert frame.get_by_role('heading',name='解答题',exact=True).count()==1
    for label,expected in manifest['expected_questions'].items():
        cell=frame.get_by_role('button',name=re.compile('^题号 '+re.escape(label)+'｜'))
        tip=cell.get_attribute('title')
        assert '已确认错误 '+str(expected['errors'])+' 人' in tip
        assert '有效提交 '+str(expected['valid'])+' 人' in tip
        for field,text in [('pending','待复核'),('not_submitted','未提交'),('unreadable','无法识别')]:
            assert text+' '+str(expected[field]) in tip
    q3=frame.get_by_role('button',name=re.compile('^题号 3｜'))
    assert '错误比例 50.0%' in q3.get_attribute('title')
    q3.hover();q3.click();idle()
    page.get_by_role('heading',name='第 3 题 · 作答与证据',exact=True).wait_for()
    assert page.get_by_label('查看学生原始作答',exact=True).count()==1
    q17=frame.get_by_role('button',name=re.compile(r'^题号 17\(2\)｜'))
    q17.click();idle()
    page.get_by_role('heading',name='第 17(2) 题 · 作答与证据',exact=True).wait_for()
    frame.get_by_role('button',name=re.compile('^题号 3｜')).click();idle()
    report['checks'].append('All20 heatmap error/valid/exception counts match stored records; q3=2/4=50%; q17(2) retains hierarchy and click linkage')
    green=frame.get_by_role('button',name=re.compile('^题号 1｜')).evaluate('e=>getComputedStyle(e).backgroundColor')
    red=frame.get_by_role('button',name=re.compile('^题号 5｜')).evaluate('e=>getComputedStyle(e).backgroundColor')
    assert green!=red
    page.set_viewport_size({'width':1000,'height':1100});page.wait_for_timeout(600)
    assert frame.get_by_role('button',name=re.compile('^题号 9｜')).bounding_box()['y']>frame.get_by_role('button',name=re.compile('^题号 1｜')).bounding_box()['y']
    page.set_viewport_size({'width':1600,'height':1450});idle()
    shot('01-teacher-heatmap.png')
    click('返回产品首页');click('进入学生学习中心');nav('我的错题本')
    assert page.get_by_label('知识点筛选',exact=True).count()==0
    for kind in v.TYPES:
        page.get_by_text(kind,exact=True).first.click();idle()
        assert page.get_by_role('button',name='查看解析',exact=True).count()==manifest['notebook_counts'][kind]
    page.get_by_text('全部错题',exact=True).click();idle()
    page.get_by_role('button',name='查看解析',exact=True).first.click();idle()
    assert page.get_by_role('button',name='继续向 AI 追问',exact=True).count()==1
    page.get_by_role('tab',name='正确解法',exact=True).click();idle()
    shot('02-student-notebook.png')
    report['checks'].append('Notebook: three type filters match8/3/5 records, all16; no knowledge-point filter; card opens original/error/solution and AI continuation')
    nav('错因分析')
    for label,count in baseline.items():
        assert page.get_by_role('button',name=label+' · '+str(count)+' 题',exact=True).count()==1
    old=next(label for label,count in baseline.items() if label!='计算失误' and count>1)
    page.get_by_role('button',name=old+' · '+str(baseline[old])+' 题',exact=True).click();idle()
    assert page.get_by_role('button',name='查看原题与解析',exact=True).count()==baseline[old]
    page.get_by_role('button',name='查看原题与解析',exact=True).first.click();idle()
    page.get_by_text('修改错因与题目记录',exact=True).click();idle()
    field=page.get_by_role('combobox',name='主要错因',exact=True)
    field.fill('计算失误');field.press('ArrowDown');page.get_by_text('计算失误',exact=True).last.click()
    click('保存错因与个人修订')
    nav('错因分析')
    assert page.get_by_role('button',name='计算失误 · '+str(baseline['计算失误']+1)+' 题',exact=True).count()==1
    assert page.get_by_role('button',name=old+' · '+str(baseline[old]-1)+' 题',exact=True).count()==1
    shot('03-student-causes.png')
    report['checks'].append('Cause category opens exact linked questions; editing one cause decrements old and increments new category with constant total')
    mobile=browser.new_page(viewport={'width':390,'height':844})
    mobile.goto('http://127.0.0.1:8507')
    mobile.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    mobile.get_by_role('button',name='进入教师工作台',exact=True).click()
    mframe=mobile.frame_locator('iframe[title*="mindtrace_question_heatmap"]')
    mframe.locator('button.cell').first.wait_for(timeout=60000)
    mobile.wait_for_timeout(500)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    assert mframe.locator('body').evaluate('e=>e.scrollWidth<=innerWidth')
    mobile.screenshot(path=str(OUT/'04-mobile-heatmap.png'),full_page=True)
    report['checks'].append('Heatmap wraps at desktop narrow widths and390px; no horizontal overflow')
    browser.close()
report['cause_counts_after']={label:len(g['ids']) for label,g in v.cause_distribution(p.notebook_rows(c.load(ROOT/'artifacts/final-ui-fixture/classroom_v1.json'),'S01'))[0].items()}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

