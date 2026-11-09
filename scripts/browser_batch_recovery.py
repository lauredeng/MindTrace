"""Real Chrome acceptance on explicit offline failures; no paid calls."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/batch-recovery';OUT.mkdir(exist_ok=True)
checks=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 for mode,status,action,count in [('全部失败','批改失败','重试未完成的批改',1),('深析失败','批改部分完成','重试未完成的批改',2),('限流暂停','批改已暂停','继续未完成的批改',1)]:
  page=b.new_page(viewport={'width':1550,'height':1250})
  page.goto('http://127.0.0.1:8509')
  page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
  def idle():
   page.wait_for_timeout(500)
   page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=60000)
   assert page.locator('[data-testid=stException]').count()==0
  def select(value):
   field=page.get_by_role('combobox',name='离线故障场景',exact=True);field.fill(value);field.press('ArrowDown');page.get_by_role('option',name=value,exact=True).click();idle()
  def click(label):page.get_by_role('button',name=label,exact=True).click();idle()
  if mode!='全部失败':select(mode)
  click('进入教师工作台');click('开始批改')
  page.get_by_text(status,exact=True).wait_for(timeout=60000)
  assert page.get_by_role('button',name=action,exact=True).is_enabled()
  assert '离线请求尝试：'+str(count) in page.inner_text('body')
  assert '不是0%' in page.inner_text('body') or '不表示0%' in page.inner_text('body')
  page.locator('[data-testid=stMain]').evaluate('e=>e.scrollTo(0,0)');page.screenshot(path=str(OUT/(str(len(checks)+1)+'-state.png')),full_page=True)
  click('班级错误分析');click('作业批改')
  assert '离线请求尝试：'+str(count) in page.inner_text('body')
  select('恢复正常');click(action)
  page.get_by_text('批改已完成',exact=True).wait_for(timeout=60000)
  assert '离线请求尝试：3' in page.inner_text('body')
  assert '尚未完成教师复核' in page.inner_text('body')
  if mode=='限流暂停':
   page.locator('[data-testid=stMain]').evaluate('e=>e.scrollTo(0,0)');page.screenshot(path=str(OUT/'4-recovered-awaiting-review.png'),full_page=True)
  click('确认这份批改')
  assert '尚未完成教师复核' not in page.inner_text('body')
  assert page.get_by_text('0.0%',exact=True).count()==1
  checks.append({'scenario':mode,'shown_status':status,'attempts_before_retry':count,'attempts_after_retry':3,'reviewed_correctness':'0.0%','passed':True})
  page.close()
 b.close()
report={'transport':'explicit offline faults and responses; no live model calls','checks':checks}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:3 fault/recovery paths, explicit retry, no automatic calls, cached successes, correctness before/after review')
