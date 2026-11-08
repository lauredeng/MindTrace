"""Teacher upload, linked evidence review, grouping and task feedback."""
import io
import json
import pandas as pd
import streamlit as st
from core import education as edu, classroom as store, ai
from ui.workbench import heading,message,dumps,digest,status,manual_form,image_input,analyze,source_panel

DECISION={'confirm':'确认','modify':'修改后确认','reject':'驳回 AI 结论','uncertain':'无法判断'}
V={'correct':'合理','incorrect':'存在错误','uncertain':'证据不足'}

def teacher(rt,review_first=False):
    heading('TEACHING INTELLIGENCE / 高中数学','把作业证据，连接到下一次进步。','图片校对 → AI 过程诊断 → 教师复核 → 学习任务 → 独立验证与反馈。')
    subs=[s for s in rt.w['submissions'] if s.get('source')!='self_study']
    successful=[s for s in subs if edu.latest_success(s)]
    cols=st.columns(4)
    values=[len(subs),len(successful),sum(bool(store.latest_review(rt.w,s['id']) and store.latest_review(rt.w,s['id'])['analysis_id']==edu.latest_success(s)['id']) for s in successful),len([t for t in rt.w['tasks'] if t.get('origin')!='self_study'])]
    for col,label,value in zip(cols,['作业题目','AI 已分析','教师已复核','学习任务'],values):
        col.metric(label,value)
    if review_first:
        review,upload,insights,feedback=st.tabs(['02 分析与证据复核','01 作业导入','03 班级共性问题','04 学习任务与反馈'])
    else:
        upload,review,insights,feedback=st.tabs(['01 作业导入','02 分析与证据复核','03 班级共性问题','04 学习任务与反馈'])
    with upload:
        left,right=st.columns([2.2,1],gap='large')
        with left,st.container(border=True,key='v1_upload'):
            pictures,manual,csv=st.tabs(['图片 · 主要入口','文本与过程','辅助 CSV'])
            with pictures:
                image_input(rt,'teacher_v1')
            with manual:
                row=manual_form('teacher')
                if row:
                    try:
                        rt.add(row)
                        st.success('材料已保存，请进入分析与复核。')
                    except ValueError as exc:
                        st.error(str(exc))
            with csv:
                file=st.file_uploader('导入辅助 CSV',type=['csv'],key='general_csv')
                if file:
                    try:
                        if file.size>1024*1024:
                            raise ValueError('CSV最多1 MB。')
                        frame=pd.read_csv(io.BytesIO(file.getvalue()),dtype=str,keep_default_na=False,encoding='utf-8-sig')
                        if not 1<=len(frame)<=100:
                            raise ValueError('每批1–100条。')
                        rows=[]
                        for raw in frame.to_dict('records'):
                            if 'student_answer' in raw and 'steps' not in raw:
                                raw=dict(raw,question='求导：'+raw['question'],tool_expression=raw['question'],task_type='derivative',steps=[],answer=raw['student_answer'])
                            edu.normalize_submission(raw)
                            rows.append(raw)
                        st.dataframe(frame.head(),hide_index=True,width='stretch')
                        if st.button('确认 CSV 材料导入'):
                            for row in rows:
                                rt.add(row,'csv')
                            st.success('导入完成，模型只在主动点击分析时调用。')
                    except (ValueError,UnicodeError,KeyError):
                        st.error('需要 student_id、question、steps或answer；兼容旧 student_answer 求导格式。')
        with right,st.container(border=True,key='v1_guide'):
            st.subheader('一条可追溯的教学链路')
            st.markdown('<div class="step-card"><span>01</span><div><b>导入与校对</b><p>确认学生归属，保留原图和步骤。</p></div></div><div class="step-card"><span>02</span><div><b>分析与复核</b><p>分开看模型判断、工具证据与教师意见。</p></div></div><div class="step-card"><span>03</span><div><b>分配学习任务</b><p>学生直接进入原题，无需重复录入。</p></div></div><div class="step-card"><span>04</span><div><b>独立训练反馈</b><p>区分提示下做对与独立完成。</p></div></div>',unsafe_allow_html=True)
            if st.button('载入跨章节匿名材料',width='stretch'):
                rows=json.loads((rt.root/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
                for row in rows:
                    rt.add(row,'constructed_examples')
                st.rerun()
            st.caption('仅载入人工构造的原始材料，没有预置 AI 诊断结果。')
    with review:
        if not subs:
            st.info('请先导入作业材料。')
        else:
            pending=[s for s in subs if not edu.latest_success(s)]
            if st.button('分析待处理作业',type='primary',disabled=not rt.ready() or not pending):
                analyze(rt,pending)
                st.rerun()
            selected=st.selectbox('选择题目 · 原文与分析联动',[s['id'] for s in subs],key='studio_selected_question',
                format_func=lambda k:next(s['student_id']+' / '+(s['question_no'] or s['topic']) for s in subs if s['id']==k))
            sub=next(s for s in subs if s['id']==selected)
            st.caption('当前状态：'+status(sub,rt.w))
            if st.button('分析 / 重新分析当前题',disabled=not rt.ready()):
                analyze(rt,[sub],True)
                st.rerun()
            original,evidence=st.columns([1,1.3],gap='large')
            with original,st.container(border=True,key='v1_source'):
                source_panel(rt,sub)
            with evidence,st.container(border=True,key='v1_evidence'):
                review_panel(rt,sub)
    with insights:
        groups=edu.class_insights(rt.w)
        if not groups:
            st.info('分析后展示可追溯的错误模式，被教师驳回的结论不进入错误分布。')
        else:
            frame=pd.DataFrame([{'模式':g['label'],'已确认':g['confirmed'],'待复核':g['pending']} for g in groups]).set_index('模式')
            st.bar_chart(frame,color=['#26745c','#b9cbb3'])
            st.caption('待复核是模型建议；优先排序综合确认程度、人数、严重性、跨题重复，不是能力分。')
            group=st.selectbox('选择错误类别追溯原作业',groups,format_func=lambda g:g['label']+f" · 确认{g['confirmed']} / 待复核{g['pending']}")
            st.write('相关学生：','、'.join(group['students']))
            st.write('跨不同题目重复：','、'.join(group['repeat_students']) or '证据不足')
            st.write('知识关联：','、'.join(group['knowledge_points']))
            st.dataframe([{'编号':s['student_id'],'题号':s['question_no'],'原题':s['question'],'状态':status(s,rt.w)}
                          for s in subs if s['id'] in group['submission_ids']],hide_index=True,width='stretch')
            if st.button('生成有证据的教学优先建议',disabled=not rt.ready()):
                try:
                    with st.spinner('依据确认状态、基础关联和典型案例生成教学建议…'):
                        advice=rt.call(ai.TEACHER_PROMPT,dumps({'groups':groups,'instruction':'考虑基础知识依赖、严重性、重复情况和证据可靠性，给教学优先级及理由；不要把待复核当事实。'}),purpose='class_advice',max_tokens=2500)
                    st.session_state.studio_advice={'basis':digest(groups),'text':advice}
                    rt.persist()
                except (RuntimeError,ValueError) as exc:
                    st.error(str(exc))
            advice=st.session_state.get('studio_advice')
            if advice and advice['basis']==digest(groups):
                message(advice['text'])
    with feedback:
        feedback_panel(rt)

def review_panel(rt,sub,allow_assignment=True,key_prefix=''):
    if not sub['analyses']:
        st.info('材料已保存，尚未分析。')
        return
    last=sub['analyses'][-1]
    if last['status']=='failed':
        st.error('最近一次未完成：'+last['error'])
    result=edu.latest_success(sub)
    if not result:
        return
    a=result['analysis']
    st.caption('AI 诊断草稿 · 不是教师最终结论')
    message(a['method_summary'])
    st.write('首个可确认错误步骤：',a['first_error_step'] or '无法定位 / 仅最终答案有证据')
    for conflict in result['conflicts']:
        st.error(conflict+' 请重点复核。')
    for step in a['steps']:
        with st.expander(f"{step['number']:02d} · {V[step['verdict']]} · {step['evidence_quote'][:32]}",expanded=step['verdict']!='correct'):
            st.text('原文：'+step['evidence_quote'])
            message(step['observation'])
    for note in a['uncertainties']:
        st.warning(note)
    with st.expander('辅助数学工具证据'):
        st.caption(result['tool']['scope'])
        if not result['tool']['checks']:
            st.info('工具不适用，AI 分析仍继续；不能声称完整证明已形式化核验。')
        for check in result['tool']['checks']:
            st.write(check)
        if result['tool'].get('expected_answer'):
            st.code(result['tool']['expected_answer'])
    with st.expander('认知假设 · 支持、反对与待确认'):
        for h in a['hypotheses']:
            st.write(h)
    previous=store.latest_review(rt.w,sub['id'])
    if previous and previous['analysis_id']!=result['id']:
        previous=None
    label=previous['label'] if previous else (a['error_patterns'][0]['label'] if a['error_patterns'] else '当前未发现已确认错误')
    with st.form('review_v1_'+key_prefix+sub['id']+result['id']):
        options=list(DECISION)
        decision=st.selectbox('教师复核结论',options,format_func=lambda k:DECISION[k],index=options.index(previous['decision']) if previous else 0)
        is_error=st.checkbox('属于需要干预的错误',value=previous.get('is_error',True) if previous else a['overall']=='error_found')
        label=st.text_input('确认或修改错误模式',value=label,max_chars=160)
        points=st.text_input('知识点 · 逗号分隔',value='，'.join(previous['knowledge_points'] if previous else a['knowledge_points']),max_chars=1000)
        first=st.number_input('教师确认的首个错误步骤（0表示无法定位）',0,len(sub['steps']),value=int(previous.get('first_error_step') or 0) if previous else int(a['first_error_step'] or 0))
        note=st.text_area('教师备注 / 修改依据',value=previous['note'] if previous else '',max_chars=2000)
        submit=st.form_submit_button('保存复核并更新统计',type='primary')
    if submit:
        store.review(rt.w,sub['id'],decision,label,[x.strip() for x in points.replace('，',',').split(',') if x.strip()],
                     note,'review-'+store.uid(),first_error_step=first or None,is_error=is_error)
        rt.persist()
        st.rerun()
    reviewed=store.latest_review(rt.w,sub['id'])
    if allow_assignment and reviewed and reviewed['decision'] in ('confirm','modify'):
        with st.form('assign_'+sub['id']+reviewed['id']):
            st.markdown('**把确认结果变成学习任务**')
            goal=st.text_area('训练目标',value='针对“'+reviewed['label']+'”理解数学依据，再用结构变化的新题独立验证。',max_chars=2000)
            mode=st.radio('建议学习方式',['quick','deep'],format_func=lambda k:'快速纠错' if k=='quick' else '深度辅导',horizontal=True)
            submit=st.form_submit_button('分配给该学生',type='primary')
        if submit:
            store.assign(rt.w,sub['id'],goal,mode,'assign-'+reviewed['id']+digest([goal,mode]))
            rt.persist()
            st.success('任务已创建，学生中心可直接进入原始错题。')
    with st.expander('模型与教师判断的版本历史'):
        st.caption(f"{len(sub['analyses'])} 次分析")
        st.dataframe([r for r in rt.w['reviews'] if r['submission_id']==sub['id']],hide_index=True,width='stretch')

def feedback_panel(rt):
    tasks=[t for t in rt.w['tasks'] if t.get('origin')!='self_study']
    if not tasks:
        st.info('复核后可直接为该学生分配学习任务。')
    else:
        rows=[]
        for task in tasks:
            attempts=[a for a in rt.w['attempts'] if a['task_id']==task['id']]
            rows.append({'编号':task['student_id'],'训练目标':task['goal'],'任务状态':task['status'],
                         '学习证据状态':edu.learning_state(attempts),'练习次数':len(attempts)})
        st.dataframe(rows,hide_index=True,width='stretch')
        task=st.selectbox('查看任务反馈',tasks,format_func=lambda t:t['student_id']+' · '+t['goal'][:45])
        st.caption('仅展示与此教学任务关联的练习证据，不展示其他自主学习对话。')
        for attempt in [a for a in rt.w['attempts'] if a['task_id']==task['id']]:
            with st.expander(attempt['created_at'][:16]+' · '+edu.learning_state([attempt])):
                message(attempt['exercise_question'])
                st.text('作答：'+attempt['answer'])
                st.write('独立性记录：',attempt['independent'],'工具支持：',attempt['independently_verified'])
                message(attempt['explanation'])
        st.download_button('下载该学生学习任务包',dumps(edu.task_package(rt.w,task)),'mindtrace_task.json','application/json')
    with st.expander('接收其他浏览器返回的任务反馈'):
        file=st.file_uploader('上传学生反馈 JSON',type=['json'],key='feedback_import')
        if file and st.button('核对关联并导入反馈'):
            try:
                count=edu.import_feedback(rt.w,file.getvalue())
                rt.persist()
                st.success(f'已导入{count}条，重复项已跳过。')
                st.warning('包文件不等于身份认证；独立性仍待复核，工具会在教师端重跑。')
            except (ValueError,OSError):
                st.error('反馈包无效、过大或不属于当前任务。')

