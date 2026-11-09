"""Task-oriented student flow, evidence states and request metadata."""
import pandas as pd
import streamlit as st
from core import education as edu, classroom as store
from ui.workbench import heading,message,dumps,manual_form,image_input,source_panel,VERDICT

def student(rt, view='tasks'):
    heading('MY LEARNING STUDIO / 学生学习中心','从一道真实错题，走向一次独立完成。','接收任务或自主提交；跳过追问、分级提示和独立训练由你选择。')
    if view=='photo':
        self_tab,assigned=st.tabs(['自主拍题 / 文本学习','我的学习任务'])
    else:
        assigned,self_tab=st.tabs(['我的学习任务','自主拍题 / 文本学习'])
    with self_tab:
        photo,text_tab=st.tabs(['拍题与校对','文本与过程'])
        with photo:
            saved=image_input(rt,'student_v1',True)
            if saved:
                st.session_state.self_submission_id=saved[0]['id']
        with text_tab:
            row=manual_form('self')
            if row:
                try:
                    sub=rt.add(row,'self_study')
                    st.session_state.self_submission_id=sub['id']
                except ValueError as exc:
                    st.error(str(exc))
        sub=next((s for s in rt.w['submissions'] if s['id']==st.session_state.get('self_submission_id')),None)
        if sub:
            st.caption('当前自主材料：'+sub['question'][:100])
            mode=st.radio('学习方式',['quick','deep'],format_func=lambda k:'快速纠错' if k=='quick' else '深度辅导',horizontal=True,key='self_mode')
            if st.button('分析并建立自主任务',disabled=not rt.ready(),type='primary'):
                result=edu.analyze_submission(sub,rt.call)
                if result['status']=='completed':
                    command='self-'+sub['id']+'-'+result['id']
                    if not any(t.get('command_id')==command for t in rt.w['tasks']):
                        task={'id':store.uid(),'command_id':command,'origin':'self_study','student_id':sub['student_id'],
                              'submission_id':sub['id'],'review_id':'self-unreviewed','goal':result['analysis']['recommendation'],
                              'confirmed_label':'AI建议，尚未教师确认','teacher_note':'自主学习，认知原因仍是待验证假设。',
                              'knowledge_points':result['analysis']['knowledge_points'],'mode':mode,'created_at':store.now(),'status':'assigned'}
                        store.commit(rt.w,command,lambda w:w['tasks'].append(task))
                    rt.persist()
                    st.success('已建立自主任务，可在“我的学习任务”进入。')
                else:
                    rt.persist()
                    st.error(result['error'])
    with assigned:
        with st.expander('导入老师发来的任务包'):
            file=st.file_uploader('选择学习任务 JSON',type=['json'],key='task_import')
            if file and st.button('读取任务与原始错题'):
                try:
                    edu.import_task_package(rt.w,file.getvalue())
                    rt.persist()
                    st.success('已读取原题与作答，无需重新录入。')
                except (ValueError,OSError):
                    st.error('任务包归属、格式或大小无效。')
        if not rt.w['tasks']:
            st.markdown('<div class="empty-state student-empty"><b>你的下一次进步，从一道题开始。</b><p>收到老师的任务包后，可以直接进入原始错题。<br>也可以点击上方「自主拍题 / 文本学习」，从自己的困惑开始。</p><div class="learning-pipeline"><span>理解问题</span><span>分级提示</span><span>独立训练</span><span>记录证据</span></div></div>',unsafe_allow_html=True)
            return
        student_ids=sorted({t['student_id'] for t in rt.w['tasks']})
        current=rt.assigned_student or st.session_state.get('studio_legacy_student')
        sid=st.selectbox('我的匿名学习编号',student_ids,index=student_ids.index(current) if current in student_ids else None)
        if sid is None:return
        st.session_state['studio_legacy_student']=sid
        own=[t for t in rt.w['tasks'] if t['student_id']==sid]
        focus=st.session_state.pop('focus_task_id',None)
        task_ids=[t['id'] for t in own]
        task_id=st.selectbox('选择学习任务',task_ids,index=task_ids.index(focus) if focus in task_ids else 0,
                            format_func=lambda k:next(t['goal'][:65] for t in own if t['id']==k))
        task=next(t for t in rt.w['tasks'] if t['id']==task_id)
        sub=next(s for s in rt.w['submissions'] if s['id']==task['submission_id'])
        if task['status']=='needs_recheck':
            st.warning('教师诊断已修改。历史保留，请等待老师根据新结论重新分配。')
            return
        left,right=st.columns([1,1.6],gap='large')
        with left,st.container(border=True,key='v1_goal'):
            st.subheader('这次要解决什么')
            message(task['goal'])
            st.caption('知识点：'+'、'.join(task['knowledge_points']))
            if task.get('imported'):
                st.caption('来自任务包，请只导入可信老师提供的匿名材料。')
            with st.expander('原题、原作答与任务依据',expanded=True):
                source_panel(rt,edu.student_material(rt.w,sub))
                st.caption('含多个学生的整页图不向学生展示；任务包仅包含该题已校对的文字。')
                st.markdown('**任务依据**')
                st.write(task['confirmed_label'])
                st.write(task['teacher_note'])
        with right,st.container(border=True,key='v1_learning'):
            learning=next((l for l in reversed(rt.w['learning']) if l['task_id']==task['id']),None)
            if not learning:
                if st.button('开始这次学习',type='primary'):
                    item=edu.new_learning(task,sub)
                    def begin(w):
                        w['learning'].append(item)
                        next(t for t in w['tasks'] if t['id']==task['id'])['status']='in_progress'
                    store.commit(rt.w,'learning-'+task['id'],begin)
                    rt.persist()
                    st.rerun()
                return
            learning_controls(rt,learning,task,sub)

def learning_controls(rt,learning,task,sub):
    attempts=[a for a in rt.w['attempts'] if a['learning_id']==learning['id']]
    st.subheader('你的学习进程')
    stage={'diagnosis':0,'tutoring':1,'training':2,'verification':3,'completed':3}.get(learning['stage'],0)
    st.markdown('<div class="learning-pipeline">'+''.join('<span class="'+('active' if i==stage else '')+'">'+label+'</span>' for i,label in enumerate(['发现问题','理清思路','独立训练','证据反馈']))+'</div>',unsafe_allow_html=True)
    st.info(edu.learning_state(attempts))
    st.caption(f"追问 {learning['questions_asked']}/3 · 提示等级 {learning['hint_level']}/4 · {len(attempts)} 次练习验证")
    for turn in learning['turns']:
        if turn['student_reply']:
            with st.chat_message('user'):
                st.write(turn['student_reply'])
        with st.chat_message('assistant'):
            message(turn['message'])
            st.caption('这次的目的：'+turn['purpose'])
    if learning['ended']:
        st.success('本次学习已结束。长期保持和迁移能力仍需后续证据。')
    else:
        a,b,c=st.columns(3)
        question=a.button('先问我一个诊断问题',disabled=not rt.ready() or learning['questions_asked']>=3)
        explain=b.button('跳过追问，快速讲解',disabled=not rt.ready())
        hint=c.button('更详细一级提示',disabled=not rt.ready() or learning['hint_level']>=4)
        with st.form('reply_'+learning['id']):
            reply=st.text_area('回答追问 / 说明卡住的地方',max_chars=2000)
            submit=st.form_submit_button('发送学习证据',disabled=not rt.ready())
        action='question' if question else 'explain' if explain else 'hint' if hint else 'reply' if submit else None
        if action:
            try:
                with st.spinner('根据新的学习证据调整…'):
                    edu.tutor_turn(learning,task,sub,action,reply if submit else '',rt.call,store.uid())
                rt.persist()
                st.rerun()
            except (RuntimeError,ValueError) as exc:
                rt.persist()
                st.error(str(exc))
        if st.button('直接生成针对性独立练习',type='primary',disabled=not rt.ready()):
            try:
                with st.spinner('生成有训练目的的变式，并尝试核验参考解…'):
                    edu.generate_exercise(learning,task,sub,rt.call)
                rt.persist()
                st.rerun()
            except (RuntimeError,ValueError) as exc:
                rt.persist()
                st.error(str(exc))
    ex=learning.get('exercise')
    if ex:
        st.divider()
        st.subheader('独立训练 · 先做，再看答案')
        message(ex['question'])
        st.caption('训练目标：'+ex['objective'])
        with st.expander('与原错误的关系及参考解检查状态'):
            message(ex['relation_to_error'])
            message(ex['structure_change'])
            st.caption('参考解局部工具状态：'+ex['reference_tool']['status']+'；复杂题仍需教师复核。')
        if not learning['ended']:
            a,b=st.columns(2)
            if a.button('练习方向提示',key='practice_hint_'+ex['id']):
                ex['hint_used']=True
                rt.persist()
            if b.button('显示完整参考解',key='practice_answer_'+ex['id']):
                ex['answer_revealed']=True
                rt.persist()
            if ex['hint_used']:
                st.info(ex['objective']+'\n'+ex['relation_to_error'])
            if ex['answer_revealed']:
                for line in ex['reference_steps']:
                    message(line)
                message(ex['answer'])
                st.caption('已查看参考解，本题后续正确不计为独立完成。')
            with st.form('attempt_'+ex['id']):
                answer=st.text_area('本次练习答案',max_chars=2000)
                steps=st.text_area('本次练习过程 · 每行一步',max_chars=8000)
                grade=st.form_submit_button('提交并验证这次作答',type='primary',disabled=not rt.ready())
            if grade:
                try:
                    with st.spinner('核对当前解法与证据…'):
                        item=edu.grade_attempt(learning,task,answer,steps,rt.call,rt.w['attempts'])
                    if not any(a['id']==item['id'] for a in rt.w['attempts']):
                        store.commit(rt.w,'attempt-'+item['fingerprint'],lambda w:w['attempts'].append(item))
                    rt.persist()
                    st.rerun()
                except (RuntimeError,ValueError) as exc:
                    rt.persist()
                    st.error(str(exc))
    for attempt in attempts:
        with st.expander('练习记录 · '+edu.learning_state([attempt]),expanded=attempt==attempts[-1]):
            message(attempt['explanation'])
            st.write('使用提示：',attempt['hint_used'],'独立工具证据：',attempt['independently_verified'])
            for note in attempt['uncertainties']:
                st.warning(note)
    if not learning['ended'] and st.button('结束本次学习并反馈任务结果'):
        learning['ended'],learning['stage']=True,'completed'
        task['status']='completed'
        rt.persist()
        st.rerun()
    st.download_button('下载本任务学习反馈包',dumps(edu.feedback_package(rt.w,task)),'mindtrace_feedback.json','application/json')
    with st.expander('认知假设如何随证据变化'):
        for h in learning['hypotheses']:
            st.write(h)
        st.caption('没有把“我懂了”或一次正确转化为长期掌握分数。')

def profiles(rt):
    heading('LEARNING EVIDENCE / 可解释学习画像','学习状态，来自具体作答。','分开记录提示下完成、独立完成和迁移表现，不生成无依据的掌握百分比。')
    ids=sorted({s['student_id'] for s in rt.w['submissions']})
    if not ids:
        st.info('暂无学习证据。请先提交材料或完成任务。')
        return
    current=rt.assigned_student or st.session_state.get('studio_legacy_student')
    sid=st.selectbox('查看匿名学习编号',ids,index=ids.index(current) if current in ids else None)
    if sid is None:return
    tasks=[t for t in rt.w['tasks'] if t['student_id']==sid]
    attempts=[a for a in rt.w['attempts'] if a['student_id']==sid]
    a,b,c=st.columns(3)
    a.metric('学习任务',len(tasks))
    b.metric('独立作答记录',sum(bool(a['independent']) for a in attempts))
    c.metric('工具支持的当前通过',sum(a['verdict']=='correct' and a['independent'] and a['independently_verified'] for a in attempts))
    for task in tasks:
        selected=[a for a in attempts if a['task_id']==task['id']]
        with st.container(border=True):
            st.markdown('**'+task['goal']+'**')
            st.write('状态：'+edu.learning_state(selected))
            st.caption('知识点：'+'、'.join(task['knowledge_points']))
            st.dataframe([{'新题':a['exercise_question'],'结果':VERDICT[a['verdict']],'使用提示':a['hint_used'],
                           '工具支持':a['independently_verified'],'时间':a['created_at'][:16]} for a in selected],hide_index=True,width='stretch')
    st.caption('编号选择器是演示，不是身份认证；跨会话长期记录和公开权限尚需正式部署方案。')

def records(rt):
    heading('TRACEABLE WORKFLOW / 调用与任务记录','每个判断，保留来源与版本。','模型分析、教师意见和学生反馈分别保存；刷新不会自动重新调用模型。')
    st.caption('会话隔离，刷新或关闭可能丢失，请下载备份。' if rt.shared else '本机 classroom_v1.json 单独保存，旧 JSON 文件保留。')
    rt.persist()
    st.download_button('下载当前教学工作区 JSON',dumps(rt.w),'mindtrace_classroom.json','application/json')
    st.caption('备份包含本工作区所有匿名学生材料，仅供教师保管；分发给学生请使用单任务包。原图不包含在此JSON中。')
    usage=rt.w['usage']
    a,b,c=st.columns(3)
    a.metric('请求尝试记录',len(usage))
    b.metric('已返回输入 tokens',sum(e.get('prompt_tokens') or 0 for e in usage))
    c.metric('已返回输出 tokens',sum(e.get('completion_tokens') or 0 for e in usage))
    if usage:
        from core.usage import by_purpose
        st.subheader('按处理阶段汇总')
        st.dataframe(by_purpose(usage),hide_index=True,width='stretch',column_config={
            'purpose':'阶段','requests':'请求次数','completed':'接口成功','truncated':'截断',
            'invalid_json':'格式异常','blocked':'本地限流','prompt_tokens':'输入 tokens',
            'completion_tokens':'输出 tokens','request_seconds':'请求累计秒数',
            'estimated_cost':'已计价响应估算','priced_responses':'有估算的响应数'})
        with st.expander('查看单次请求记录'):
            st.dataframe(pd.DataFrame(usage).drop(columns=['session_id'],errors='ignore'),hide_index=True,width='stretch')
    st.caption('usage来自真实接口响应，失败可能没有usage。费用需配置单价才估算，缓存折扣未建模，不是服务商账单。')
    with st.expander('幂等操作与版本记录'):
        st.dataframe(pd.DataFrame(rt.w['events']),hide_index=True,width='stretch')

