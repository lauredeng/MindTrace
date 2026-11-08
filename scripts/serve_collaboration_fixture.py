"""Offline two-browser acceptance only. No real model transport or user data."""
import os,sys,runpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
os.environ['MINDTRACE_ENV']='production';os.environ['MINDTRACE_SHARED_MODE']='1'
os.environ['MINDTRACE_ENABLE_DEVELOPER_MODE']='0'
os.environ['MINDTRACE_DATA_DIR']=str(ROOT/'artifacts/collab-e2e-data')
os.environ['MINDTRACE_CLASSROOM_DIR']=str(ROOT/'artifacts/collab-e2e-classrooms')
import streamlit as st
from core import ai
from test_product import quick,deep,correction
from test_education import CASES
st.warning('双浏览器隔离验收：OCR和模型响应为明确的离线模拟，非真实识别或教学效果评测。')
def offline(messages,**kw):
 purpose=kw['purpose']
 if purpose=='ocr':
  assert any(x.get('type')=='image_url' and x['image_url']['url'].startswith('data:image/') for x in messages[1]['content'])
  return {'transcription':'离线构造样例：A、B两位学生，同一道方程原始作答。','warnings':['离线验收草稿，必须人工确认。'],
   'records':[dict(CASES[10],student_id=sid,question_type='解答题') for sid in ('A','B')]}
 raw=json.loads(messages[1]['content'])
 if purpose=='quick_grading':return quick(raw)
 if purpose=='error_analysis':return deep(raw)
 if purpose=='study_dialogue':return {'message':'离线解释：括号中的每一项都要乘2。','purpose':'解释本题去括号的依据','next_suggestion':'检查原来第二步是否漏乘常数项。'}
 if purpose=='solve_question':return {'known_conditions':['原方程已给出'],'goal':'求x','method':'等式两边作相同变形','correction':correction()}
 raise ValueError('Unexpected isolated acceptance purpose')
ai.ai_ready=lambda:True;ai.completion=offline
runpy.run_path(str(ROOT/'app.py'),run_name='__main__')
