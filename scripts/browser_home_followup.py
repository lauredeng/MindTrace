from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('artifacts/home-followup');out.mkdir(exist_ok=True)
import time,urllib.request
for attempt in range(60):
 try:
  if urllib.request.urlopen('http://127.0.0.1:8508/_stcore/health',timeout=2).read()==b'ok':break
 except OSError:time.sleep(.25)
else:raise RuntimeError('Acceptance server is not ready')
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=b.new_page(viewport={'width':1550,'height':1300})
 page.goto('http://127.0.0.1:8508');page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
 def idle():
  page.wait_for_timeout(700)
  assert page.locator('[data-testid=stException]').count()==0
 def shot(n):page.screenshot(path=str(out/(n+'.png')),full_page=True)
 teacher=page.locator('.st-key-home_select_teacher button');student=page.locator('.st-key-home_select_student button')
 assert teacher.get_attribute('kind')=='primary'
 student.click();idle()
 assert student.get_attribute('kind')=='primary' and teacher.get_attribute('kind')=='secondary'
 assert page.get_by_role('button',name='进入教师工作台',exact=True).count()==1
 shot('01-student-preselected')
 teacher.click();idle();assert teacher.get_attribute('kind')=='primary';shot('02-teacher-preselected')
 page.get_by_role('button',name='进入教师工作台',exact=True).click();idle()
 page.get_by_role('button',name='上传新作业',exact=True).click();idle()
 zone=page.locator('[data-testid=stFileUploaderDropzone]').first
 zone.scroll_into_view_if_needed();idle()
 assert zone.locator('[data-testid=stFileUploaderDropzoneInstructions]').evaluate('e=>getComputedStyle(e,"::before").content').find('拖拽图片')>=0
 assert zone.locator('button').bounding_box()['x']>zone.locator('[data-testid=stFileUploaderDropzoneInstructions]').bounding_box()['x']
 shot('03-upload')
 page.locator('[data-testid=stSidebar]').get_by_role('button',name='学生',exact=True).click();idle()
 page.locator('[data-testid=stSidebar]').get_by_role('button',name='我的错题本',exact=True).click();idle()
 page.get_by_role('button',name='查看解析',exact=True).first.click();idle()
 page.get_by_role('button',name='继续向 AI 追问',exact=True).click();idle()
 page.get_by_role('heading',name='AI解题与辅导',exact=True).wait_for(timeout=60000)
 page.get_by_role('heading',name='题目与原有解答',exact=True).scroll_into_view_if_needed();idle()
 shot('04-followup-page')
 page.get_by_role('heading',name='继续追问这道题',exact=True).scroll_into_view_if_needed();idle()
 shot('05-followup-input')
 print('PASS: reversible card preselection, separate enter buttons, upload actual DOM, notebook-to-follow-up original question and input')
 b.close()
