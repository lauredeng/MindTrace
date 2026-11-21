"""Single handoff to official tutoring; old loops are not run in this mode."""
import streamlit as st
from core import tutor_client


def handoff(rt,sub=None,*,key='official_tutor'):
    if not tutor_client.configured():return False
    st.subheader('循理学习空间')
    st.write('围绕原题连续辅导，结合教师反馈理解关键步骤，并将订正回传课堂。')
    if not rt.access or rt.access.get('role')!='student':
        st.info('请先连接学生课堂，再进入个人辅导。')
        return True
    if st.button('进入本题辅导' if sub else '进入我的学习空间',type='primary',key=key):
        try:
            rt.persist(strict=True)
            url=tutor_client.launch(rt.access['code'],sub['id'] if sub else None)
            st.session_state[key+'_url']=url
        except (ValueError,RuntimeError):
            st.error('学习空间暂时无法连接。已有作业仍保留，请确认辅导服务已经启动。')
    url=st.session_state.get(key+'_url')
    if url:st.link_button('打开学习空间',url,type='primary',key=key+'_link')
    return True
