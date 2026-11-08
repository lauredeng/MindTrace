"""Isolated browser transport fixture. Run only for tests on a local test port."""
import os,sys,json,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['MINDTRACE_ENV']='development'
os.environ['MINDTRACE_SHARED_MODE']='0'
os.environ['MINDTRACE_ENABLE_DEVELOPER_MODE']='0'
os.environ['MINDTRACE_DATA_DIR']=str(ROOT/'artifacts/v12-browser-offline-data')
from core import ai,product as p,education as e
import streamlit as st
ai.ai_ready=lambda:True
def correction():
    return {'answer':'x=2','steps':[{'text':'2*x+6=10','reason':'乘法分配律'},{'text':'2*x=4','reason':'等式两边减6'},{'text':'x=2','reason':'两边除以非零数2'}],
        'knowledge_points':['乘法分配律'],'category':'公式或定理误用','category_basis':'离线模拟：本题去括号遗漏了常数项上的因子，原因仍待本人确认。',
        'supplements':[{'kind':'formula','content':'a(b+c)=ab+ac','conditions':'实数乘法的分配律','connection':'本题括号中x与3都需要乘2'}],
        'uncertainties':['浏览器离线模拟响应，不是本次真实模型判断。']}
def offline(messages,**kw):
    purpose=kw['purpose']
    path=ROOT/'artifacts/v12-browser-offline-calls.json'
    calls=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    calls.append(purpose);path.write_text(json.dumps(calls),encoding='utf-8')
    if purpose=='ocr':
        return {'transcription':'构造印刷材料：STU-01、STU-02，解方程2*(x+3)=10，原始错误步骤。',
            'warnings':['离线模拟OCR返回，需校对。'],'records':[
            {'student_id':sid,'question_no':'Q1','question':'解方程2*(x+3)=10',
             'steps':['2*(x+3)=10','2*x+3=10','2*x=7','x=3.5'],'answer':'x=3.5','topic':'综合应用与证明','uncertainties':[]}
             for sid in ('STU-01','STU-02')]}
    raw=json.loads(messages[1]['content'])
    if purpose=='quick_grading':
        return {'verdict':'incorrect','final_answer_status':'incorrect','basis':'离线模拟：去括号时漏乘常数项。',
            'evidence_id':'S2','evidence_quote':raw['steps'][1],'first_error_step':2,'knowledge_points':['乘法分配律'],
            'category':'公式或定理误用','category_basis':'本题候选原因，仍需本人确认。','process_checked':True}
    if purpose=='error_analysis':
        return {'topic':raw['topic'],'knowledge_points':['乘法分配律'],'method_summary':'离线模拟：第2步去括号时，3也应乘2。',
            'overall':'error_found','final_answer_status':'incorrect','steps':[{'number':i,'verdict':'incorrect' if i==2 else 'correct',
            'observation':'应将括号内两项分别乘2。' if i==2 else '此步相对上一式成立。','evidence_quote':line} for i,line in enumerate(raw['steps'],1)],
            'first_error_step':2,'error_patterns':[{'label':'分配律展开遗漏常数项因子','step_numbers':[2],'severity':2,'evidence_quote':raw['steps'][1]}],
            'hypotheses':[{'id':'H1','description':'可能遗漏分配律的作用范围','support':['原步骤'],'against':[],'open_questions':['括号内每一项都乘2了吗？']}],
            'uncertainties':['离线模拟，不能作为真实模型效果证据。'],'recommendation':'解释分配律，再自行判断。','correction':correction()}
    if purpose=='solve_question':
        return {'known_conditions':['2*(x+3)=10'],'goal':'求未知数x','method':'先去括号再等价变形。','correction':correction()}
    if purpose=='study_dialogue':
        return {'message':'离线模拟：等式两边同时除以2，可得x+3=5；因为2非零，变形等价。',
                'purpose':'解释等式同除非零数的依据','next_suggestion':'也可以继续问去括号的另一种解法。'}
    raise ValueError('Unexpected fixture purpose')
ai.completion=offline
if not hasattr(p,'_browser_fixture_create_batch'):
    p._browser_fixture_create_batch=p.create_batch
def create_batch(w,name,rows,source='image_confirmed'):
    return p._browser_fixture_create_batch(w,name,rows,'offline_browser_fixture')
p.create_batch=create_batch
st.warning('隔离浏览器测试：模型响应为离线模拟，不是真实AI调用结果。')
runpy.run_path(str(ROOT/'app.py'),run_name='__main__')

