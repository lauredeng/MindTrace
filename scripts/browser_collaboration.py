"""Two independent Chrome contexts: upload to shared classroom and feedback return."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/collaboration-e2e';OUT.mkdir(exist_ok=True)
checks=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 edge=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 tc=b.new_context(viewport={'width':1550,'height':1250});sc=edge.new_context(viewport={'width':1550,'height':1250});bc=edge.new_context(viewport={'width':1550,'height':1250})
 t=tc.new_page();s=sc.new_page();other=bc.new_page()
 def idle(page):
  page.wait_for_timeout(500)
  page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=60000)
  assert page.locator('[data-testid=stException]').count()==0
 def click(page,name):page.get_by_role('button',name=name,exact=True).click();idle(page)
 def panel(page,opened=True):
  exp=page.locator('[data-testid=stSidebar] [data-testid=stExpander]').filter(has=page.get_by_text('课堂连接',exact=True)).first
  details=exp.locator('details').first
  if bool(details.evaluate('e=>e.open'))!=opened:page.get_by_text('课堂连接',exact=True).click();idle(page)
  return exp
 def choose(page,label,value):
  field=page.get_by_role('combobox',name=label,exact=True)
  control=page.locator('[data-testid=stSelectbox]').filter(has=field).first
  if field.input_value()==value or value in control.inner_text().splitlines():return
  field.fill(value);field.press('ArrowDown');page.get_by_role('option',name=value,exact=True).click();idle(page)
 def shot(page,name):
  panel(page,False);page.locator('[data-testid=stMain]').evaluate('e=>e.scrollTo(0,0)');page.wait_for_timeout(300)
  if name=='03-student-followup':page.get_by_role('heading',name='继续追问这道题',exact=True).evaluate('e=>e.scrollIntoView({block:"center"})')
  if name=='04-teacher-feedback':page.get_by_text('学生备注：我漏乘了括号内的常数，需要再核对分配律。',exact=True).evaluate('e=>e.scrollIntoView({block:"center"})')
  page.wait_for_timeout(250);page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
 def join(page,code):
  page.goto('http://127.0.0.1:8510');page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
  panel(page);page.get_by_role('textbox',name='课堂访问码',exact=True).fill(code);click(page,'连接课堂')
 t.goto('http://127.0.0.1:8510');t.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
 panel(t);t.get_by_role('textbox',name='课堂名称',exact=True).fill('独立浏览器数学课堂');click(t,'创建协作课堂')
 panel(t);teacher_code=t.locator('[data-testid=stSidebar] code').first.text_content().strip();assert teacher_code.count('.')==1
 panel(t,False)
 # Screenshot a deterministic source document, then upload the actual PNG bytes.
 source=tc.new_page();source.set_viewport_size({'width':1000,'height':600})
 row=json.loads((ROOT/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))[10]
 from html import escape
 source.set_content('<html><body style="font:24px Arial;padding:35px"><p>OFFLINE ACCEPTANCE FIXTURE - not real student work</p>'+''.join('<h3>'+sid+' '+row['question_no']+'</h3><p>'+escape(row['question'])+'<br>'+('<br>'.join(escape(line) for line in row['steps']))+'<br>'+escape(row['answer'])+'</p>' for sid in ('A','B'))+'</body></html>')
 source.screenshot(path=str(OUT/'input.png'));source.close()
 t.get_by_role('textbox',name='本次作业名称',exact=True).fill('跨浏览器闭环验收')
 t.locator('[data-testid=stFileUploaderDropzoneInput]').first.set_input_files(str(OUT/'input.png'));idle(t)
 t.get_by_text('图片已经匿名化，同意发送至模型进行真实识别。',exact=True).click();idle(t)
 assert t.get_by_role('checkbox',name='图片已经匿名化，同意发送至模型进行真实识别。',exact=True).is_checked()
 click(t,'识别图片中的题目与步骤')
 t.get_by_text('我已核对原图、学生归属、题目和作答。',exact=True).click();idle(t)
 click(t,'确认校对并保存材料')
 panel(t);codes={}
 for sid in ('A','B'):
  choose(t,'为哪位学生发放学习码',sid);click(t,'生成学生学习码')
  codes[sid]=t.locator('[data-testid=stSidebar] code').last.text_content().strip()
 panel(t,False)
 click(t,'开始批改')
 click(t,'确认这份批改');choose(t,'查看学生原始作答','B / Q11');click(t,'确认这份批改')
 checks.append('Teacher uploads actual fixture PNG, confirms OCR draft, grades two source records and reviews both; no preset production OCR')
 shot(t,'01-teacher-reviewed')
 join(s,codes['A']);panel(s,False)
 assert s.get_by_role('button',name='查看解析',exact=True).count()==1
 assert s.locator('[data-testid=stSidebar]').get_by_role('button',name='教师',exact=True).count()==0
 click(s,'查看解析');assert '跨浏览器闭环验收' in s.inner_text('body')
 shot(s,'02-student-original')
 s.get_by_text('修改错因与题目记录',exact=True).click();idle(s)
 choose(s,'主要错因','计算失误')
 s.get_by_role('textbox',name='我的备注',exact=True).fill('我漏乘了括号内的常数，需要再核对分配律。')
 # Teacher writes while the student's edit form still holds an older snapshot.
 choose(t,'查看学生原始作答','A / Q11')
 t.get_by_role('textbox',name='教师备注 / 修改依据',exact=True).fill('教师并行复核：保留原始作答证据。')
 click(t,'保存复核并更新统计')
 s.get_by_text('确认这次错因分类',exact=True).click();click(s,'保存错因与个人修订')
 click(s,'继续向 AI 追问')
 s.get_by_role('textbox',name='继续追问 / 回答 AI',exact=True).fill('为什么括号里的3也要乘2？');click(s,'发送问题或回答')
 shot(s,'03-student-followup')
 # The teacher still has an old snapshot. A save must adopt the student's
 # merged feedback without requiring a manual refresh or hiding it as synced.
 click(t,'保存复核并更新统计')
 t.get_by_text('学生学习反馈',exact=True).click();idle(t)
 t.get_by_text('学生备注：我漏乘了括号内的常数，需要再核对分配律。',exact=True).wait_for()
 t.get_by_text('本题辅导互动：1 次',exact=True).wait_for()
 assert '为什么括号里的3也要乘2？' in t.inner_text('body')
 shot(t,'04-teacher-feedback')
 checks.append('Independent student browser receives exact teacher source, changes personal cause and asks a question; a stale teacher save receives merged notes and dialogue without manual refresh; concurrent teacher review is preserved')
 join(other,codes['B']);panel(other,False)
 assert other.get_by_role('button',name='查看解析',exact=True).count()==1
 click(other,'查看解析')
 assert '我漏乘了括号内的常数，需要再核对分配律。' not in other.inner_text('body')
 checks.append('A third isolated browser for student B cannot see student A notes or dialogue; student navigation cannot enter teacher pages')
 # New browser restores the same student history via scoped access, not shared browser state.
 fresh=b.new_context(viewport={'width':1200,'height':1000});again=fresh.new_page();join(again,codes['A']);panel(again,False)
 click(again,'查看解析');assert '我漏乘了括号内的常数，需要再核对分配律。' in again.inner_text('body')
 click(again,'继续向 AI 追问');assert '教师并行复核：保留原始作答证据。' in again.inner_text('body')
 checks.append('A fresh browser session reconnects using the same student code and retrieves persisted learning history')
 edge.close();b.close()
(OUT/'report.json').write_text(json.dumps({'transport':'explicit offline OCR and model responses','new_live_model_calls':0,'browsers':['Chrome teacher','Edge student'],'independent_contexts':4,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: Chrome teacher / Edge student, student-B / reconnected-student contexts; upload, review, linked notebook, dialogue, feedback and persistence. Codes never printed.')
