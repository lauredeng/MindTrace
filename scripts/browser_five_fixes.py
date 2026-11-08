from pathlib import Path
from playwright.sync_api import sync_playwright
import json,sys
sys.path.insert(0,str(Path.cwd()))
from core import classroom as c,presentation as v
out=Path('artifacts/five-fixes');out.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=b.new_page(viewport={'width':1550,'height':1200})
 page.goto('http://127.0.0.1:8508');page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
 a=page.locator('.st-key-v11_surface_home_teacher').bounding_box();z=page.locator('.st-key-v11_surface_home_student').bounding_box()
 print('Home card sizes:',{k:round(a[k],1) for k in ['width','height']},{k:round(z[k],1) for k in ['width','height']})
 assert abs(a['width']-z['width'])<2 and abs(a['height']-z['height'])<2
 assert page.get_by_role('combobox',name='工作空间',exact=True).count()==0
 page.screenshot(path=str(out/'01-home.png'),full_page=True)
 page.get_by_role('button',name='进入教师工作台',exact=True).click()
 page.get_by_text('平均正确率',exact=True).wait_for(timeout=60000)
 w=c.load(Path('artifacts/academic-ui-fixture/classroom_v1.json'));summary=v.batch_summary(w,w['batches'][-1]['id'])
 assert page.get_by_text(f"{summary['correctness']:.1%}",exact=True).count()==1
 heat=page.frame_locator('iframe[title*="mindtrace_question_heatmap"]');heat.get_by_role('button',name=__import__('re').compile(r'^题号 3｜')).click()
 page.get_by_role('heading',name='第 3 题 · 作答与证据',exact=True).wait_for(timeout=60000)
 link=page.get_by_role('link',name='查看原始作答与分析证据 ↓');link.click();page.wait_for_timeout(400)
 assert page.locator('#question-evidence').evaluate('e=>e.getBoundingClientRect().top')<400
 page.locator('[data-testid=stMain]').evaluate('e=>e.scrollTo(0,0)');page.wait_for_timeout(400)
 page.screenshot(path=str(out/'02-teacher-correctness.png'),full_page=True)
 page.locator('[data-testid=stSidebar]').get_by_role('button',name='学生',exact=True).click()
 page.locator('[data-testid=stSidebar]').get_by_role('button',name='我的错题本',exact=True).click()
 page.get_by_role('button',name='查看解析',exact=True).first.wait_for(timeout=60000)
 assert page.locator('[data-testid=stRadio]').count()==0
 page.get_by_text('填空题',exact=True).first.click();page.wait_for_timeout(700)
 assert page.get_by_role('button',name='查看解析',exact=True).count()==3
 page.get_by_text('全部错题',exact=True).first.click();page.wait_for_timeout(600)
 page.get_by_role('button',name='查看解析',exact=True).first.click();page.wait_for_timeout(600)
 question=page.get_by_role('heading',name='错题详情',exact=True).bounding_box()
 follow=page.get_by_role('button',name='继续向 AI 追问',exact=True).bounding_box()
 assert follow['y']>question['y']+150
 page.get_by_role('tab',name='正确解法',exact=True).click();page.wait_for_timeout(400)
 page.screenshot(path=str(out/'03-notebook-followup.png'),full_page=True)
 page.get_by_role('button',name='继续向 AI 追问',exact=True).click()
 page.get_by_role('heading',name='AI解题与辅导',exact=True).wait_for(timeout=60000)
 assert page.locator('[data-testid=stException]').count()==0
 print('PASS: equal home cards, fixed workspace buttons, correctness source, heatmap detail link, segmented categories, follow-up position and route')
 b.close()
