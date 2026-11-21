"""Explicit offline product UI fixture; never imported by the public app."""
import sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from core import classroom as c,product as p,presentation as v,learning_records as learning,review_scheduler as review
from ui.learning_hub import student_workspace,teacher_corrections
from ui.design import page_header

ROOT=Path(__file__).resolve().parents[1]
st.set_page_config(page_title='循理 · 学习闭环离线验收',layout='wide')
st.markdown('<style>'+(ROOT/'assets/style.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
st.caption('离线构造材料 · 仅验证交互、数据关联及调度，不代表真实识别或数学批改效果。')
if 'platform_workspace' not in st.session_state:
    w=c.new_workspace();w['student_roster']=['001','002','003']
    rows=[]
    for sid in ('001','002'):
        rows.extend([
            dict(student_id=sid,question_no='19',question_type='解答题',topic='函数与导数',
                 question=r'已知函数 $f(x)=x^3-3x$，若直线 $y=m$ 与函数图像有三个不同交点，求实数 $m$ 的取值范围，并说明理由。',
                 steps=[r"$f'(x)=3x^2-3$",r'$f(-1)=2，f(1)=-2$',r'$m\in[-2,2]$'],answer='[-2,2]'),
            dict(student_id=sid,question_no='9',question_type='多选题',topic='函数与导数',
                 question=r'已知 $f(x)=x^3-3x$。下列说法正确的是：A. $f$ 为奇函数；B. $f$ 在实数集上单调递增；C. $x=-1$ 是极大值点；D. $f(x)=0$ 只有一个实根。',
                 steps=[],answer='A')])
    batch=p.create_batch(w,'函数与导数 · 周练',rows,'constructed_examples',grading_policy=p.CLASSROOM_POLICY)
    for sid in batch['submission_ids']:
        v.override_grade(w,sid,'incorrect','原答需修正：区间端点应排除；多选题需核对完整选项。')
        p.sync_notebook(w,sid)
    sub=next(s for s in w['submissions'] if s['student_id']=='001' and s['question_no']=='19')
    attempt=learning.submit_correction(w,sub['id'],'001',[r"$f'(x)=3(x-1)(x+1)$",'根据三个单调区间及极值，水平线高度应严格介于两个极值之间。'],r'$-2<m<2$',command_id='fixture-correction')
    learning.assess_correction(w,attempt['id'],'correct','已结合单调区间与极值排除端点，订正依据完整。',command_id='fixture-review')
    unit=review.add_unit(w,sub['id'],'001',when=datetime.now(timezone.utc)-timedelta(days=2))
    st.session_state.platform_workspace=w


class Runtime:
    root=ROOT
    shared=True
    assigned_student='001'
    access=None
    key=None
    session='offline-platform-fixture'
    def __init__(self):self.w=st.session_state.platform_workspace
    def ready(self):return False
    def persist(self,*,strict=False):c.validate_workspace(self.w)
    def prepare_workspace(self):return self.w
    def image(self,ref):return None
    def call(self,*a,**k):raise AssertionError('Offline fixture forbids model calls')


with st.sidebar:
    st.markdown('### MindTrace 循理 AI')
    mode=st.radio('页面',['订正与复习','学习画像','教师反馈','批改工作台'])
rt=Runtime()
if mode=='学习画像':student_workspace(rt,view='profile')
elif mode=='教师反馈':
    page_header('学生订正反馈','结合原答与新过程，确认本次订正是否解决了问题。','教师工作台 / 学习闭环')
    sub=next(s for s in rt.w['submissions'] if s['student_id']=='001' and s['question_no']=='19')
    st.markdown(sub['question']);teacher_corrections(rt,sub)
elif mode=='批改工作台':
    from ui.product import teacher
    rt.assigned_student=None;teacher(rt)
else:student_workspace(rt)
