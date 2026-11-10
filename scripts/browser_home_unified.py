import re
from pathlib import Path
from sys import argv
from playwright.sync_api import expect, sync_playwright
out=Path('artifacts/home-unified');out.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=b.new_page(viewport={'width':1550,'height':1200});page.goto(argv[1] if len(argv)>1 else 'http://127.0.0.1:8501')
 page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
 card=page.locator('.st-key-v11_surface_home_teacher')
 student=page.locator('.st-key-v11_surface_home_student')
 expect(card).to_have_css('background-image', re.compile('linear-gradient'))
 before=student.bounding_box();student.hover()
 expect(student).to_have_css('background-image', re.compile('linear-gradient'))
 expect(card).to_have_css('background-image','none')
 page.wait_for_timeout(500);after=student.bounding_box()
 assert after['width']>before['width']*1.01
 card.hover()
 assert 'linear-gradient' in card.evaluate('e=>getComputedStyle(e).backgroundImage')
 expect(student).to_have_css('background-image','none')
 assert page.locator('.st-key-home_select_teacher button').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgba(0, 0, 0, 0)'
 page.mouse.move(0,0);page.wait_for_timeout(400)
 expect(student).to_have_css('background-image','none')
 page.screenshot(path=str(out/'01-teacher.png'),full_page=True)
 student_button=page.locator('.st-key-home_select_student button')
 student.hover()
 student_button.click()
 expect(student_button).to_have_attribute('kind','primary',timeout=12000)
 assert page.get_by_role('button',name='进入教师工作台',exact=True).count()==1
 page.mouse.move(0,0);page.wait_for_timeout(400)
 page.screenshot(path=str(out/'02-student.png'),full_page=True)
 page.get_by_role('button',name='进入学生学习中心',exact=True).click()
 page.get_by_role('heading',name='AI解题与辅导',exact=True).wait_for(timeout=60000)
 assert page.locator('[data-testid=stException]').count()==0
 page.get_by_role('button',name='返回产品首页',exact=True).click();page.wait_for_timeout(500)
 page.set_viewport_size({'width':390,'height':1000});page.wait_for_timeout(400)
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 b.close()
 print('PASS: unified background, hover enlargement, selection then entry, mobile width')
