"""Actual Chrome E2E with explicitly labelled offline model transport on port8506."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/v12-browser-offline';OUT.mkdir(exist_ok=True)
if not (ROOT/'artifacts/v12-offline-upload.png').exists():
    from PIL import Image,ImageDraw,ImageFont
    im=Image.new('RGB',(1000,850),'white');draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24)
    for n,sid in enumerate(('STU-01','STU-02')):
        for i,line in enumerate([f'匿名编号 {sid}  Q1','解方程2*(x+3)=10','2*(x+3)=10','2*x+3=10','2*x=7','x=3.5']):
            draw.text((50,40+n*400+i*48),line,font=font,fill='#22334f')
    im.save(ROOT/'artifacts/v12-offline-upload.png')
report={'transport':'explicit offline fixture, not actual API quality','checks':[],'page_errors':[],'human_usability_test':False}
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=b.new_page(viewport={'width':1600,'height':1200})
    page.on('pageerror',lambda err:report['page_errors'].append(str(err)))
    def idle():
        page.wait_for_timeout(500)
        page.wait_for_function("document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state') !== 'running'",timeout=60000)
        page.wait_for_timeout(250)
        assert page.locator('[data-testid=stException]').count()==0
    def click(label):
        page.get_by_role('button',name=label,exact=True).click();idle()
    def nav(label):
        page.locator('[data-testid=stSidebar]').get_by_text(label,exact=True).click();idle()
    def shot(name):
        idle();page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
    page.goto('http://127.0.0.1:8506',wait_until='networkidle')
    page.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    click('进入教师工作台')
    if not page.get_by_role('button',name='识别图片中的题目与步骤',exact=True).is_visible():
        page.get_by_text('上传作业与确认识别',exact=True).click();idle()
    page.locator('input[type=file]').first.set_input_files(str(ROOT/'artifacts/v12-offline-upload.png'))
    idle()
    page.get_by_text('图片已经匿名化，同意发送至模型进行真实识别。',exact=True).click();idle()
    click('识别图片中的题目与步骤')
    page.get_by_role('checkbox',name='我已核对原图、学生归属、题目和作答。',exact=True).wait_for()
    shot('01-recognized-draft')
    page.get_by_text('我已核对原图、学生归属、题目和作答。',exact=True).click();idle()
    click('确认校对并保存材料')
    click('开始批改')
    shot('02-layered-grading')
    # Review only the selected case, not a forced batch-wide confirmation.
    page.get_by_role('button',name='保存复核并更新统计',exact=True).first.click();idle()
    nav('班级学情')
    shot('03-class-question-statistics')
    assert page.get_by_label('选择题目查看学生与依据',exact=True).count()==1
    assert page.get_by_label('选择相似错误类别',exact=True).count()==1
    report['checks'].append('Teacher: upload printed fixture, inspect OCR draft, confirm, batch both layers, review and inspect per-question/common-error evidence')
    nav('历史记录');shot('04-history-export')
    click('返回产品首页');click('进入学生学习中心')
    profile=page.get_by_role('combobox',name='匿名学习编号',exact=True)
    profile.fill('STU-01');profile.press('ArrowDown')
    page.get_by_text('STU-01',exact=True).last.click();idle()
    page.get_by_text('查看完整解答',exact=True).click();idle()
    click('获取所选讲解')
    click('请 AI 主动问我一个关键问题')
    page.get_by_label('继续追问 / 回答 AI',exact=True).fill('为什么两边都可以除以2？')
    click('发送问题或回答')
    shot('05-student-follow-up')
    nav('我的错题本')
    field=page.get_by_role('combobox',name='主要错因',exact=True)
    field.fill('公式或定理遗忘')
    field.press('ArrowDown')
    page.get_by_text('公式或定理遗忘',exact=True).last.click()
    if not page.get_by_role('checkbox',name='确认这次错因分类',exact=True).is_checked():
        page.get_by_text('确认这次错因分类',exact=True).click()
    click('保存错因与个人修订')
    click('按当前错因补充讲解')
    shot('06-notebook-formula')
    nav('错因分析')
    assert page.get_by_text('公式或定理遗忘',exact=True).count()>0
    shot('07-cause-statistics')
    click('打开这道错题的原文与解析')
    report['checks'].append('Student: reads teacher original without reentry, requests full solution, active prompt plus free question, edits cause, gets formula/conditions and drills into linked statistics')
    nav('AI 解题与辅导')
    page.get_by_text('上传题目或补充文字',exact=True).click();idle()
    page.get_by_role('tab',name='文字输入',exact=True).click();idle()
    # Same math, a new explicit anonymous profile, no original work.
    page.get_by_label('匿名学习编号',exact=True).last.fill('SELF-NOANSWER')
    page.get_by_label('完整题目与条件',exact=True).fill('解方程2*(x+3)=10')
    click('保存作业材料')
    page.get_by_text('查看完整解答',exact=True).click();idle()
    click('获取所选讲解')
    click('加入 / 更新我的错题本')
    shot('08-no-answer-direct-solve')
    report['checks'].append('No-answer: can save only a problem, directly solve and collect with no mandatory task or training')
    mobile=b.new_page(viewport={'width':390,'height':844})
    mobile.goto('http://127.0.0.1:8506')
    mobile.get_by_role('button',name='进入教师工作台',exact=True).wait_for(timeout=60000)
    mobile.screenshot(path=str(OUT/'09-mobile-home.png'),full_page=True)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    mobile.get_by_role('button',name='进入学生学习中心',exact=True).click()
    mobile.get_by_role('heading',name='拍下问题，选择你需要的解释。',exact=True).wait_for(timeout=30000)
    mobile.wait_for_timeout(700)
    mobile.screenshot(path=str(OUT/'10-mobile-student.png'),full_page=True)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    report['checks'].append('Mobile: home/student rendered at390px without document overflow')
    b.close()
report['offline_calls']=json.loads((ROOT/'artifacts/v12-browser-offline-calls.json').read_text(encoding='utf-8'))
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

