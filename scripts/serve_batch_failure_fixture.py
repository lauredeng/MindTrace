"""LOCAL ACCEPTANCE ONLY: explicit offline transport; never run as production app."""
import os,sys,runpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
os.environ['MINDTRACE_ENV']='production';os.environ['MINDTRACE_SHARED_MODE']='1'
os.environ['MINDTRACE_ENABLE_DEVELOPER_MODE']='0'
os.environ['MINDTRACE_DATA_DIR']=str(ROOT/'artifacts/batch-recovery-fixture')
import streamlit as st
from core import ai,classroom as c,product as p
from core.limits import UsageLimitError
from test_product import quick,deep
from test_education import CASES
st.warning('隔离验收：使用离线故障和响应，不调用真实AI，不保存用户数据。')
mode=st.selectbox('离线故障场景',['全部失败','深析失败','限流暂停','恢复正常'],key='batch_fixture_mode')
if 'studio_workspace' not in st.session_state:
 w=c.new_workspace();p.create_batch(w,'故障恢复验收（离线模拟）',[CASES[10]],'offline_browser_fixture')
 st.session_state['studio_workspace']=w
 st.session_state['batch_fixture_calls']=[]
st.caption('离线请求尝试：'+str(len(st.session_state['batch_fixture_calls'])))
def offline(messages,**kw):
 purpose=kw['purpose'];st.session_state['batch_fixture_calls'].append(purpose)
 if mode=='限流暂停':raise UsageLimitError('操作较频繁，请稍候再试；这是离线限流模拟。')
 if mode=='全部失败' or mode=='深析失败' and purpose=='error_analysis':raise RuntimeError('离线模拟服务失败，请稍后重试。')
 sub=st.session_state['studio_workspace']['submissions'][0]
 return quick(sub) if purpose=='quick_grading' else deep(sub)
ai.ai_ready=lambda:True
ai.completion=offline
runpy.run_path(str(ROOT/'app.py'),run_name='__main__')
