"""Display saved real API decisions; no new model calls from this replay service."""
import os,sys,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['MINDTRACE_ENV']='production';os.environ['MINDTRACE_SHARED_MODE']='1';os.environ['MINDTRACE_ENABLE_DEVELOPER_MODE']='0'
os.environ['MINDTRACE_DATA_DIR']=str(ROOT/'artifacts/agent-replay-data')
import streamlit as st
from core import ai,classroom as c
candidates=sorted((ROOT/'artifacts/agent-live').glob('*/case-1.json'),key=lambda p:p.stat().st_mtime)
if not candidates:st.error('需要先完成真实接口小样本检查。');st.stop()
if 'studio_workspace' not in st.session_state:st.session_state['studio_workspace']=c.load(candidates[-1])
ai.ai_ready=lambda:False
st.warning('真实DeepSeek结果回放：构造数学材料，展示已完成的模型决策与实际数学工具结果；本页面不发送新请求。')
runpy.run_path(str(ROOT/'app.py'),run_name='__main__')
