from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('artifacts/home-unified');out.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=b.new_page(viewport={'width':1550,'height':1200});page.goto('http://127.0.0.1:8501')
 page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
 card=page.locator('.st-key-v11_surface_home_teacher')
 before=card.bounding_box();card.hover();page.wait_for_timeout(400);after=card.bounding_box()
 assert after['width']>before['width']*1.01
 assert 'linear-gradient' in card.evaluate('e=>getComputedStyle(e).backgroundImage')
 assert page.locator('.st-key-home_select_teacher button').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgba(0, 0, 0, 0)'
 page.mouse.move(280,160);page.wait_for_timeout(400)
 page.screenshot(path=str(out/'01-teacher.png'),full_page=True)
 page.locator('.st-key-home_select_student button').click();page.wait_for_timeout(700)
 assert page.locator('.st-key-home_select_student button').get_attribute('kind')=='primary'
 assert page.get_by_role('button',name='进入教师工作台',exact=True).count()==1
 page.mouse.move(280,160);page.wait_for_timeout(400)
 page.screenshot(path=str(out/'02-student.png'),full_page=True)
 page.get_by_role('button',name='进入学生学习中心',exact=True).click()
 page.get_by_role('heading',name='AI解题与辅导',exact=True).wait_for(timeout=60000)
 assert page.locator('[data-testid=stException]').count()==0
 page.get_by_role('button',name='返回产品首页',exact=True).click();page.wait_for_timeout(500)
 page.set_viewport_size({'width':390,'height':1000});page.wait_for_timeout(400)
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 b.close()
 print('PASS: unified background, hover enlargement, selection then entry, mobile width')
