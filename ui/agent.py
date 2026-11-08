"""Student-facing bounded tutoring controls and evidence summaries."""
import streamlit as st
from core import agent as a,education as e,classroom as c
from ui.workbench import message

def _invoke(rt,fn,*args,**kwargs):
    try:return fn(rt.w,*args,**kwargs,_prepare=rt.prepare_agent,_persist=rt.persist)
    except (ValueError,RuntimeError):
        st.warning('本次操作未完成，请检查输入；若另一窗口正在处理，请稍后刷新查看。');st.stop()

def render(rt,sub):
    sid=sub['student_id'];current=a.latest_run(rt.w,sub['id'],sid)
    st.caption('围绕这道题选择追问、讲解或局部核验；需要你回答时会暂停。你随时可以切换到直接答疑。')
    if not current or current['status']=='cancelled':
        if st.button('开始深度辅导',type='primary',disabled=not rt.ready(),key='agent_start_'+sub['id']):
            with st.spinner('根据原题选择下一步帮助…'):_invoke(rt,a.run,sub['id'],sid,rt.call,command_id=c.uid())
            st.rerun()
    if current:
        allowed=[t for t in current['trace'] if t.get('policy')=='allowed']
        if allowed:st.markdown('**当前目标：** '+allowed[-1]['goal'])
        st.info(a.STATUSES.get(current['status'],'本次辅导已记录'))
        if current.get('needs_teacher_review') and not getattr(rt,'access',None):st.caption('复核需求已保存在当前工作区；尚未连接课堂，不会发送给教师。')
        if current['status'] in ('paused','failed','stopped'):
            st.warning(current.get('message','本次已暂停。'))
        if current['status'] in ('paused','failed'):
            if st.button('继续暂停的辅导',disabled=not rt.ready(),key='agent_resume_'+current['id']):
                with st.spinner('从已保存的步骤继续…'):_invoke(rt,a.run,sub['id'],sid,rt.call,resume=True)
                st.rerun()
    row=next((r for r in rt.w['study_sessions'] if r['submission_id']==sub['id'] and r['student_id']==sid),{})
    for turn in row.get('turns',[])[-8:]:
        if not turn.get('agent_run_id'):continue
        with st.container(border=True):
            if turn['reply']:st.write('我的回答：'+turn['reply'])
            message(turn['message']);st.caption('这次在解决：'+turn['purpose'])
    if current and current['status'] in ('waiting_consent','practice_blocked'):
        st.caption('新题验证由你选择；只有参考解通过现有局部数学核验才发布。')
        if st.button('愿意，生成一道验证题',disabled=not rt.ready(),key='agent_accept_'+current['id']):
            with st.spinner('生成并核对参考解…'):_invoke(rt,a.accept_practice,sub['id'],sid,rt.call)
            st.rerun()
    if current and current.get('practice_error'):st.warning(current['practice_error'])
    practice=(current or {}).get('practice')
    if practice and practice['learning'].get('exercise'):
        ex=practice['learning']['exercise'];st.subheader('自愿的新题验证');message(ex['question'])
        st.caption(ex['objective']+' 工具仅支持局部核验，不构成完整证明。')
        if st.button('查看练习参考解',key='agent_answer_'+ex['id']):
            ex['answer_revealed']=True;rt.persist();st.rerun()
        if ex['answer_revealed']:
            message(ex['answer'])
            for line in ex['reference_steps']:message(line)
        with st.form('agent_practice_'+ex['id']):
            answer=st.text_area('验证题答案',max_chars=2000)
            steps=st.text_area('验证题过程 · 每行一步',max_chars=8000)
            submit=st.form_submit_button('提交验证题',disabled=not rt.ready())
        if submit:
            try:
                with st.spinner('结合题目和步骤核对…'):_invoke(rt,a.check_practice,sub['id'],sid,answer,steps,rt.call)
                st.rerun()
            except (ValueError,RuntimeError):rt.persist();st.error('本次验证未完成，请检查作答内容或稍后重试。')
        if practice['attempts']:
            last=practice['attempts'][-1]
            st.info(e.learning_state(practice['attempts']));message(last['explanation'])
            st.caption('这是当前这道验证题的证据，不代表长期掌握。')
            if st.button('结合验证结果继续辅导',disabled=not rt.ready(),key='agent_after_practice_'+ex['id']):
                with st.spinner('根据新题证据选择下一步…'):
                    _invoke(rt,a.run,sub['id'],sid,rt.call,reply='请结合刚才的验证题作答，帮助我决定下一步。',command_id=c.uid())
                st.rerun()
    older=[r['practice'] for r in row.get('agent_runs',[]) if r.get('practice',{}).get('attempts') and r is not current]
    if older:
        with st.expander('本题的验证记录'):
            for record in older[-3:]:
                message(record['learning']['exercise']['question'])
                st.caption(e.learning_state(record['attempts'])+'；仅代表当前练习证据。')
    if current:
        with st.form('agent_reply_'+sub['id'],clear_on_submit=True):
            reply=st.text_area('回答或补充你的问题',max_chars=2000,placeholder='例如：我以为括号里的常数不用乘2。')
            direct=st.checkbox('本次直接讲解，不继续追问')
            send=st.form_submit_button('发送并继续辅导',type='primary',disabled=not rt.ready())
        if send:
            if not reply.strip():st.warning('请先补充你的回答或问题。')
            else:
                try:
                    with st.spinner('结合你的回答调整帮助方式…'):
                        _invoke(rt,a.run,sub['id'],sid,rt.call,reply=reply,preference='direct' if direct else 'guided',command_id=c.uid())
                    st.rerun()
                except (ValueError,RuntimeError):rt.persist();st.error('本次辅导未完成，请检查输入或稍后重试。')
        with st.expander('本次辅导依据'):
            st.caption('这里只展示简短动作依据和实际结果，不展示内部思维过程。')
            for trace in current['trace']:
                if trace.get('policy')=='allowed':
                    st.markdown('**'+a.ACTIONS[trace['action']]+'** · '+trace['rationale'])
                    labels=[{'QUESTION':'原题','ANSWER':'原答案','REPLY':'你的回答','TEACHER_REVIEW':'教师意见','AI_ANALYSIS':'原有AI分析（待核对）','PRIOR_EXPLANATION':'先前讲解','PRACTICE_LAST':'最近验证题'}.get(k,'第'+k[1:]+'步' if k.startswith('S') else '局部核验结果') for k in trace['evidence_ids']]
                    st.caption('依据：'+'、'.join(labels))
                else:st.caption('有一个动作因不满足条件而未执行。')
                observation=trace.get('observation')
                if observation:
                    if observation.get('status')=='rejected':st.caption(observation['reason'])
                    else:
                        st.caption({'checked':'完成可用的局部核验','partial':'部分步骤可局部核验','not_applicable':'此材料超出当前工具范围'}.get(observation['status'],'核验结果需要进一步确认'))
                        for check in observation.get('checks',[]):
                            if check.get('step'):st.write('第 '+str(check['step'])+' 步：'+{'correct':'相邻变形成立','incorrect':'相邻变形不成立','baseline':'仅建立比较基准'}.get(check['verdict'],'待核对'))
                        st.caption(observation.get('meaning',''))
