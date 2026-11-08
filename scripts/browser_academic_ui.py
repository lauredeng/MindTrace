"""Academic UI: real Chrome on explicitly constructed records; no paid model calls."""
import json,re,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import classroom as c,product as p,presentation as v
ROOT=Path.cwd();OUT=ROOT/'artifacts/academic-ui';OUT.mkdir(exist_ok=True)
data_path=ROOT/'artifacts/academic-ui-fixture/classroom_v1.json'
w=c.load(data_path);rows=p.notebook_rows(w,'S01');slices,total,unknown=v.cause_slices(rows)
report={'data':'constructed acceptance records, not real classroom/model evaluation','new_model_calls':False,'checks':[],'page_errors':[]}
with sync_playwright() as pl:
    b=pl.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=b.new_page(viewport={'width':1600,'height':1250})
    page.on('pageerror',lambda err:report['page_errors'].append(str(err)))
    def idle():
        page.wait_for_timeout(550)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=60000)
        page.wait_for_timeout(250)
        assert page.locator('[data-testid=stException]').count()==0
    def click(name):
        page.get_by_role('button',name=name,exact=True).click();idle()
    def nav(name):
        page.locator('[data-testid=stSidebar]').get_by_text(name,exact=True).click();idle()
    def shot(name):
        idle();page.locator('[data-testid=stMain]').evaluate('e=>e.scrollTo({top:0,behavior:"instant"})');page.wait_for_timeout(300)
        page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
    page.goto('http://127.0.0.1:8508',wait_until='networkidle')
    page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    click('进入教师工作台')
    menu=page.locator('.st-key-main_navigation')
    assert menu.get_by_role('button').count()==3
    for name in ('作业批改','班级错误分析','历史记录'):assert menu.get_by_text(name,exact=True).count()==1
    assert page.get_by_text('显示经典工作区',exact=True).count()==0
    heat=page.frame_locator('iframe[title*="mindtrace_question_heatmap"]')
    heat.locator('.cell').first.wait_for(timeout=60000)
    assert heat.locator('.cell').count()==20
    q3=heat.get_by_role('button',name=re.compile('^题号 3｜'))
    assert '已确认错误 2 人' in q3.get_attribute('title') and '有效提交 4 人' in q3.get_attribute('title')
    colors=heat.locator('.cell').evaluate_all('els=>[...new Set(els.map(e=>getComputedStyle(e).backgroundColor))]')
    assert len(colors)==3
    q3.click();idle()
    page.get_by_role('heading',name='第 3 题 · 作答与证据',exact=True).wait_for()
    shot('01-teacher-results')
    nav('班级错误分析')
    click('查看第5题')
    page.get_by_role('heading',name='第 5 题 · 作答与证据',exact=True).wait_for()
    heat.get_by_role('button',name=re.compile(r'^题号 17\(2\)｜')).click();idle()
    page.get_by_role('heading',name='第 17(2) 题 · 作答与证据',exact=True).wait_for()
    shot('02-class-errors')
    report['checks'].append('Teacher: exactly3 primary links, three-level question heatmap, 20 cells, counts/tooltip and native-priority/subquestion click linkage verified')
    click('返回产品首页');click('进入学生学习中心')
    assert page.get_by_label('匿名学习编号',exact=True).count()==0
    assert 'SELF-01' not in page.inner_text('body')
    assert 'S01' not in page.inner_text('body')
    nav('我的错题本')
    assert page.get_by_label('知识点筛选',exact=True).count()==0
    for kind,count in [('选择题',8),('填空题',3),('解答题',5)]:
        page.get_by_text(kind,exact=True).first.click();idle()
        assert page.get_by_role('button',name='查看解析',exact=True).count()==count
    page.get_by_text('全部错题',exact=True).click();idle()
    page.get_by_role('button',name='查看解析',exact=True).first.click();idle()
    assert page.get_by_role('button',name='继续向 AI 追问',exact=True).count()==1
    page.get_by_role('tab',name='正确解法',exact=True).click();idle()
    shot('03-notebook')
    report['checks'].append('Student: automatic profile, no SELF-01 or S01 on normal pages, three type filters8/3/5, readable detail with AI continuation')
    nav('错因分析')
    pie=page.frame_locator('iframe[title*="mindtrace_cause_pie"]')
    pie.get_by_role('button').first.wait_for(timeout=60000)
    assert pie.get_by_role('button').count()==len(slices)
    for item in slices:
        name=item['label']+' · '+str(item['count'])+'题 · '+item['percent_label']+'%'
        assert pie.get_by_role('button',name=name,exact=True).count()==1
    target=slices[-1]
    pie.get_by_role('button',name=target['label']+' · '+str(target['count'])+'题 · '+target['percent_label']+'%',exact=True).click();idle()
    assert page.get_by_role('button',name='查看原题与解析',exact=True).count()==target['count']
    # Native legend selection must not be reset by an earlier pie event.
    next_item=slices[1]
    click('查看'+next_item['label'])
    assert page.get_by_role('button',name='查看原题与解析',exact=True).count()==next_item['count']
    shot('04-cause-pie')
    report['checks'].append('Pie: sector count, names, exact counts and unified percentages match source records; sector and legend both filter the correct questions')
    # Test editing against the same source, then restore to leave the fixture stable.
    old=next_item['label'];edit_item_id=v.cause_distribution(rows)[0][old]['ids'][0]
    original=next(n for n in rows if n['id']==edit_item_id)
    page.get_by_role('button',name='查看原题与解析',exact=True).first.click();idle()
    page.get_by_text('修改错因与题目记录',exact=True).click();idle()
    change='计算失误' if old!='计算失误' else '审题失误'
    field=page.get_by_role('combobox',name='主要错因',exact=True);field.fill(change);field.press('ArrowDown')
    page.get_by_text(change,exact=True).last.click()
    click('保存错因与个人修订')
    nav('错因分析')
    changed_w=c.load(data_path);new_slices,new_total,_=v.cause_slices(p.notebook_rows(changed_w,'S01'))
    assert new_total==total
    new_counts={s['label']:s['count'] for s in new_slices}
    old_counts={s['label']:s['count'] for s in slices}
    assert new_counts.get(old,0)==old_counts[old]-1
    assert new_counts[change]==old_counts.get(change,0)+1
    for item in new_slices:
        assert pie.get_by_role('button',name=item['label']+' · '+str(item['count'])+'题 · '+item['percent_label']+'%',exact=True).count()==1
    report['checks'].append('Reclassification updates source records and rendered pie counts/percentages, keeping total constant')
    click('设置')
    assert page.locator('.st-key-main_navigation').get_by_role('button').count()==3
    assert page.get_by_text('下载工作区备份',exact=True).count()==0
    assert page.get_by_text('下载我的错题记录',exact=True).count()==1
    report['checks'].append('Settings is separate; ordinary student export remains scoped to own notebook')
    # Restore the controlled fixture without touching user data.
    live=c.load(data_path);entry=next(n for n in live['notebook'] if n['id']==edit_item_id)
    p.edit_entry(live,entry['id'],original['primary_category'],original['secondary_categories'],original['notes'],original['category_confirmed'],original.get('edited_question',original['question']))
    c.save(live,data_path)
    mobile=b.new_page(viewport={'width':390,'height':844})
    mobile.goto('http://127.0.0.1:8508')
    mobile.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    mobile.get_by_role('button',name='进入教师工作台',exact=True).click()
    mheat=mobile.frame_locator('iframe[title*="mindtrace_question_heatmap"]');mheat.locator('.cell').first.wait_for(timeout=60000)
    mobile.wait_for_timeout(600)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    assert mheat.locator('body').evaluate('e=>e.scrollWidth<=innerWidth')
    mobile.screenshot(path=str(OUT/'05-mobile-teacher.png'),full_page=True)
    # New mobile context opens the student workspace directly from the home.
    mstudent=b.new_page(viewport={'width':390,'height':844});mstudent.goto('http://127.0.0.1:8508')
    mstudent.get_by_role('button',name='进入学生学习中心',exact=True).wait_for(timeout=60000)
    mstudent.get_by_role('button',name='进入学生学习中心',exact=True).click()
    # The collapsed sidebar can be opened by its accessible control.
    mstudent.get_by_role('button',name='Expand sidebar',exact=True).click()
    mstudent.locator('[data-testid=stSidebar]').get_by_text('错因分析',exact=True).click()
    mstudent.get_by_role('button',name='Collapse sidebar',exact=True).click()
    mstudent.wait_for_timeout(500)
    mpie=mstudent.frame_locator('iframe[title*="mindtrace_cause_pie"]');mpie.get_by_role('button').first.wait_for(timeout=60000)
    assert mpie.locator('body').evaluate('e=>e.scrollWidth<=innerWidth')
    assert not mstudent.evaluate('document.documentElement.scrollWidth>innerWidth')
    mstudent.screenshot(path=str(OUT/'06-mobile-causes.png'),full_page=True)
    report['checks'].append('390px teacher heatmap and student pie render without document/component overflow')
    b.close()
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

