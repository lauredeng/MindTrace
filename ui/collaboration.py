"""Lightweight classroom connections, separate from demo role switching."""
from copy import deepcopy
from urllib.parse import urlsplit, urlunsplit
import streamlit as st
from core import collaboration as collab
from core.limits import UsageLimitError

def connect(code):
    access=collab.resolve(code)
    w=collab.load(code)
    for key in list(st.session_state):
        if key.startswith(('studio_','v12_','assignment_upload_','book_','heatmap_','last_heat_','cause_','question_kinds_','scores_','score_')) or key in ('solve_mode','experience_destination','experience_page','experience_nav'):
            del st.session_state[key]
    st.session_state.pop('collab_generated_code',None)
    st.session_state.pop('collab_recovery_code',None)
    st.session_state['collab_access']=access
    if access['role']=='student':st.session_state['collab_guest']=True
    st.session_state['studio_workspace']=w
    st.session_state['collab_snapshot']=deepcopy(w)
    st.session_state['experience_role']='教师工作空间' if access['role']=='teacher' else '学生学习空间'
    st.session_state['experience_page']='作业批改' if access['role']=='teacher' else ('AI解题与辅导' if access['number_demo'] else '我的错题本')
    return access

@st.fragment(run_every=3.0)
def sync_panel():
    access=st.session_state.get('collab_access')
    if not access:return
    try:
        changed=collab.version(access['code'])!=st.session_state.get('studio_workspace',{}).get('storage_version')
        if changed:st.info('课堂有新记录，点击刷新查看。')
        if st.button('刷新课堂数据',key='refresh_collab'):
            w=collab.load(access['code']);st.session_state['studio_workspace']=w
            st.session_state['collab_snapshot']=deepcopy(w)
            st.rerun(scope='app')
    except (OSError,ValueError):st.warning('课堂连接已失效，请重新连接。')

def demo_student_form(workspace,class_id=None):
    from core.uploads import school_number
    with st.form('demo_class_join'):
        classroom=class_id or st.text_input('演示课堂码（选填）',max_chars=32,
                                            help='打开老师分享的课堂链接后，这一项会自动填好。')
        number=st.text_input('学号',max_chars=32)
        submit=st.form_submit_button('按学号查看我的作业')
    if submit:
        try:
            number=school_number(number)
            if classroom.strip():
                connect(collab.demo_code(classroom,number))
            elif not collab.has_student_number(workspace,number):
                raise ValueError('本工作区找不到该学号。请核对学号，或使用老师发的课堂链接。')
            else:
                st.session_state['studio_student_choice']=(workspace['id'],number)
                st.session_state.pop('v12_sub',None)
                st.session_state.pop('v12_sub_pending',None)
        except (OSError,ValueError) as exc:
            st.error('未找到这个演示课堂和学号的组合，请核对链接和学号。' if classroom.strip() else str(exc))
        else:
            st.rerun()


def connection_panel():
    access=st.session_state.get('collab_access')
    if access:
        try:
            access=collab.resolve(access['code']);st.session_state['collab_access']=access
        except (OSError,ValueError):
            st.session_state.pop('collab_access',None);st.session_state.pop('studio_workspace',None)
            for key in list(st.session_state):
                if key.startswith('assignment_upload_'):del st.session_state[key]
            st.session_state.pop('collab_snapshot',None);st.warning('课堂访问码已失效，请重新连接。');access=None
    demo_link=st.query_params.get('class','')
    if demo_link and not access and not st.session_state.get('experience_role'):
        st.session_state['experience_role']='学生学习空间'
        st.session_state['experience_page']='AI解题与辅导'
    with st.expander('课堂连接',expanded=False):
        if not access:
            st.caption('老师可创建课堂。已有课堂访问码时，直接输入即可连接。')
            name=st.text_input('课堂名称',value='我的数学课堂',max_chars=80,key='collab_name')
            number_demo=st.checkbox('创建按学号进入的演示课堂（仅使用虚构学号和作答）')
            if st.button('创建协作课堂',key='create_collab'):
                try:
                    code=collab.create(name,creator_id=st.session_state.get('ai_usage_id','server-script'),
                                       number_demo=number_demo);connect(code)
                    st.session_state['collab_recovery_code']=code;st.rerun()
                except UsageLimitError:st.warning('创建课堂过于频繁或数量已达上限，请稍后再试；已有访问码仍可连接课堂。')
                except (ValueError,OSError,RuntimeError):st.error('无法创建课堂，请检查服务器存储配置。')
            code=st.text_input('课堂访问码',type='password',max_chars=130,key='collab_code_input',help='学生填写老师发放的个人学习码；教师填写自己的恢复码。')
            if st.button('连接课堂',key='join_collab'):
                try:connect(code);st.rerun()
                except (ValueError,OSError):st.error('课堂访问码无效或已失效。')
        else:
            st.write(access['name'])
            st.caption('教师课堂' if access['role']=='teacher' else '已关联你的作业与学习记录')
            if access['role']=='student':st.caption('本课堂的作答、错因修订和追问记录会同步给教师。')
            if access['role']=='teacher':
                if st.session_state.get('collab_recovery_code')==access['code']:
                    with st.expander('保存教师恢复码（请勿分享给学生）'):
                        st.code(access['code'],language=None)
                        st.caption('服务器仅保存码的摘要，请自行妥善保管。')
                if access['number_demo']:
                    st.caption('演示课堂链接。学生打开后输入学号即可查看作业。仅使用虚构作业。')
                    url=urlsplit(getattr(st.context,'url',None) or '')
                    if url.scheme in ('http','https') and url.netloc:
                        st.code(urlunsplit((url.scheme,url.netloc,url.path or '/','class='+access['class_id'],'')),language=None)
                    st.caption('演示课堂码')
                    st.code(access['class_id'],language=None)
                w=collab.load(access['code']);students=sorted({s['student_id'] for s in w['submissions']})
                if students:
                    filenames={m['student_id']:m['pages'][0]['filename'] for b in w['batches'] for m in b.get('materials',[])
                               if m['identity_status']=='file_group'}
                    sid=st.selectbox('为哪位学生发放学习码',students,key='collab_invite_student',
                                     format_func=lambda student:filenames.get(student,student))
                    st.caption('学习码仅能访问该学生。重新生成会使该学生旧码失效。')
                    if st.button('生成学生学习码',key='issue_collab'):
                        st.session_state['collab_generated_code']=collab.invite(access['code'],sid)
                    if st.session_state.get('collab_generated_code'):
                        with st.expander('复制学生学习码，私下发给对应学生'):
                            st.code(st.session_state['collab_generated_code'],language=None)
                else:st.info('保存学生作业后，可为每位学生发放学习码。')
            if st.button('断开课堂',key='leave_collab'):
                for key in list(st.session_state):
                    if key.startswith(('collab_','studio_','v12_','assignment_upload_','book_')) and key!='collab_guest':del st.session_state[key]
                st.session_state['collab_guest']=True
                st.query_params.pop('class',None)
                st.session_state['experience_role']='产品首页';st.session_state['experience_page']='产品首页';st.rerun()
    if access:sync_panel()
    return access
