"""Real Chrome layout inspection; never submits paid model requests."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--round',type=int,default=1)
parser.add_argument('--url',default='http://127.0.0.1:8501')
args=parser.parse_args()
out=ROOT/'artifacts'/('v1-design-round-'+str(args.round))
out.mkdir(parents=True,exist_ok=True)
result={'round':args.round,'checks':[],'page_errors':[],'live_api_triggered':False}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1512,'height':1250})
    page.on('pageerror',lambda e:result['page_errors'].append(str(e)))
    page.goto(args.url,wait_until='networkidle')
    page.get_by_role('heading',name='把作业证据，连接到下一次进步。').wait_for(timeout=60000)
    page.get_by_role('button',name='载入跨章节匿名材料').wait_for(timeout=30000)
    page.wait_for_timeout(1200)
    assert page.get_by_label('开发者 DeepSeek API Key',exact=True).count()==0
    page.screenshot(path=str(out/'teacher-home.png'),full_page=True)
    result['checks'].append('Default general teacher home; no API key required')
    if args.round==1:
        page.get_by_role('button',name='载入跨章节匿名材料').click()
        page.wait_for_timeout(1000)
    page.get_by_role('tab',name='02 分析与证据复核').click()
    page.get_by_text('选择题目 · 原文与分析联动',exact=True).wait_for(timeout=15000)
    page.wait_for_timeout(700)
    page.screenshot(path=str(out/'teacher-review.png'),full_page=True)
    result['checks'].append('Linked evidence panel renders')
    page.get_by_text('学生学习中心',exact=True).first.click()
    page.get_by_role('heading',name='从一道真实错题，走向一次独立完成。').wait_for(timeout=15000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(out/'student-center.png'),full_page=True)
    result['checks'].append('Distinct student task center renders')
    page.get_by_text('学习证据画像',exact=True).first.click()
    page.get_by_role('heading',name='学习状态，来自具体作答。').wait_for(timeout=15000)
    page.wait_for_timeout(600)
    page.screenshot(path=str(out/'learning-profile.png'),full_page=True)
    result['checks'].append('Evidence profile renders')
    page.get_by_text('调用与任务记录',exact=True).first.click()
    page.get_by_role('heading',name='每个判断，保留来源与版本。').wait_for(timeout=15000)
    page.wait_for_timeout(600)
    assert page.locator('[data-testid=stException]').count()==0
    result['checks'].append('Usage and version records render')
    mobile=browser.new_page(viewport={'width':390,'height':844})
    mobile.goto(args.url)
    mobile.get_by_role('button',name='载入跨章节匿名材料').wait_for(timeout=60000)
    mobile.wait_for_timeout(1000)
    mobile.screenshot(path=str(out/'mobile-home.png'),full_page=True)
    result['mobile_overflow']=mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    result['mobile_sidebar_collapsed']=mobile.locator('[data-testid=stSidebar]').get_attribute('data-collapsed')=='true'
    assert not result['mobile_overflow']
    assert result['mobile_sidebar_collapsed']
    result['checks'].append('Mobile layout without document overflow')
    browser.close()
(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

