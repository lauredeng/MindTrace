"""Manual/browser layout fixture. Never imported by the public app; no AI calls.
Run: python -m streamlit run tests/ui_fixture.py --server.address 127.0.0.1
"""
import io
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from core import classroom as c, product as p, presentation as v
from ui.product import selected_case, notebook
from ui.results import results

st.set_page_config(page_title='MindTrace · 复核页面验收', layout='wide')
st.markdown('<style>'+ (ROOT/'assets/style.css').read_text(encoding='utf-8')+'</style>', unsafe_allow_html=True)
st.warning('界面验收用构造样例 · 无模型调用，不代表真实识别或批改效果。')


def material(answer):
    canvas=Image.new('RGB',(1000,560),'#fcfbf8')
    draw=ImageDraw.Draw(canvas)
    font_path='C:/Windows/Fonts/msyh.ttc'
    font=ImageFont.truetype(font_path,27) if Path(font_path).exists() else ImageFont.load_default(size=27)
    rows=['函数与方程 · 作答排版样例（非手写识别实测）',
          '已知 f(x) = x³ − 3x，直线 y = m 与其图像有三个',
          '不同交点，求实数 m 的取值范围，并说明理由。',
          '解：f′(x) = 3x² − 3 = 3(x − 1)(x + 1)。',
          '极大值 f(−1) = 2，极小值 f(1) = −2。',
          '由函数图像与水平直线的交点关系，可得：',
          'm ∈ '+answer]
    for i,line in enumerate(rows):
        draw.text((38,35+i*69),line,font=font,fill='#22304c' if i<3 else '#435878')
    buf=io.BytesIO();canvas.save(buf,format='PNG');return buf.getvalue()


if 'fixture_workspace' not in st.session_state:
    w=c.new_workspace();images={}
    question='已知函数 $f(x)=x^3-3x$。若直线 $y=m$ 与函数图像有三个不同交点，求实数 $m$ 的取值范围，并说明理由。'
    rows=[]
    for sid,answer in [('1001','[-2,2]'),('1002','(-2,2)'),('1003','[-2,2)')]:
        img=material(answer);ref=sha256(img).hexdigest();images[ref]=img
        rows.append(dict(student_id=sid,question=question,question_no='19',question_type='解答题',
                         steps=[r"$f'(x)=3x^2-3$",r'$f(-1)=2,\quad f(1)=-2$',r'$m\in '+answer+'$'],
                         answer=answer,image_ref=ref))
    batch=p.create_batch(w,'函数专题 · 周练',rows,source='constructed_examples',grading_policy=p.CLASSROOM_POLICY)
    for sub in w['submissions']:
        correct=sub['student_id']=='1002'
        basis='当 m 等于极值时，交点数减少，应排除端点。故 m ∈ (−2, 2)。' if not correct else '利用极大值与极小值确定水平线位置，端点排除正确。'
        p.quick_check(sub,lambda *a,_correct=correct,_basis=basis,**k:dict(
            verdict='correct' if _correct else 'incorrect',final_answer_status='correct' if _correct else 'incorrect',
            basis=_basis,evidence_id='ANSWER',first_error_step=None,process_checked=True,uncertainty_reason='other'))
    for sid in list(batch['submission_ids']):
        sub=next(s for s in w['submissions'] if s['id']==sid)
        v.override_grade(w,sid,'correct' if sub['student_id']=='1002' else 'incorrect',
                         '函数在 x=−1、x=1 处分别取得极大值2与极小值−2。三个不同交点要求 −2<m<2，不能包含端点。')
        p.sync_notebook(w,sid)
    st.session_state.fixture_workspace=w
    st.session_state.fixture_images=images
    st.session_state.fixture_batch=batch['id']


class FixtureRuntime:
    root=ROOT
    assigned_student=None
    shared=True
    access=None
    key=None
    session='offline-ui-fixture'
    def __init__(self):self.w=st.session_state.fixture_workspace
    def ready(self):return False
    def image(self,ref):return st.session_state.fixture_images.get(ref)
    def persist(self):c.validate_workspace(self.w)
    def prepare_workspace(self):return self.w
    def call(self,*a,**k):raise AssertionError('UI fixture forbids model calls')


rt=FixtureRuntime()
mode=st.radio('验收视图',['教师复核','学生错题本'],horizontal=True)
if mode=='教师复核':
    batch=next(b for b in rt.w['batches'] if b['id']==st.session_state.fixture_batch)
    results(rt,batch,selected_case)
else:
    rt.assigned_student='1001'
    notebook(rt)
