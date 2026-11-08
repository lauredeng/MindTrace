"""Confirmed-results page: question heatmap is the primary exam visualization."""
from math import isfinite
import pandas as pd
import streamlit as st
from core import presentation as v,product as p
from ui.experience import surface,badge,topic_chips,safe
from ui.heatmap import question_heatmap

def results(rt,batch,case_renderer,view='grading'):
    rows=v.heatmap_rows(rt.w,batch['id'],automatic=True)
    summary=v.batch_summary(rt.w,batch['id'],automatic=True,rows=rows)
    from ui.design import page_header,metric,note
    page_header(batch['name'] if view=='grading' else '班级错误分析',
        '批改、复核与班级结果，围绕同一份作业展开。' if view=='grading' else '从题目定位共性错误，再回到学生的原始作答。',
        '作业批改 / 批改结果' if view=='grading' else batch['name'],summary['status'])
    execution=summary['execution']
    progress_text=f"完成全部所需步骤 {execution['complete']}/{execution['total']} 份；快速批改成功 {execution['quick_completed']} 份，深析成功 {execution['deep_completed']}/{execution['deep_required']} 份。"
    if execution['status']=='failed':
        st.error('批改失败，尚无有效批改结果。'+progress_text+' 请检查服务配置或稍后重试。')
    elif execution['status']=='partial':
        st.warning('批改部分完成，仍有未完成的步骤。'+progress_text+' 请重试未完成的批改；已有结果会保留。')
    elif execution['status']=='paused':
        st.warning('批改已暂停。'+progress_text)
        st.info(batch.get('pause_reason','请求受到限制，请稍后继续。')+' 限制解除后，回到作业批改点击“继续未完成的批改”；不会重复调用已成功的步骤。')
    elif execution['status']=='processed':
        st.caption(progress_text)
    cards=st.columns(4,gap='large')
    with cards[0]:metric('提交学生',summary['submitted_students'],'同一学生提交多题仅计一人',accent=True,icon_name='people')
    with cards[1]:metric('平均正确率',f"{summary['correctness']:.1%}" if summary['correctness'] is not None else '—',
        f"正确 {summary['correct_count']} / 已判 {summary['valid_count']}",icon_name='chart')
    with cards[2]:metric('批改异常',sum(r['pending']+r['unreadable'] for r in rows),'尚未形成正误结论',icon_name='review')
    with cards[3]:metric('判错作答',sum(r['errors'] for r in rows),'包含卷面已确认的留白',icon_name='check')
    st.caption('正确率按已判正误的作答计算，留白计错。教师改判后自动更新。')
    if summary['correctness'] is None:
        st.info('尚无正误结论，平均正确率显示“—”。')
    elif any(r['pending'] or r['unreadable'] for r in rows):
        st.info('当前正确率覆盖已判作答。还有批改异常未计入分母。')
    if summary['average'] is not None:
        metric('班级平均分',f"{summary['average']:g}",f"满分 {summary['max_score']:g} · 教师已核实",icon_name='chart')
    if not rows:
        st.info('没有可展示的题目。');return
    active_key='heatmap_selected_'+batch['id']
    ids=[r['id'] for r in rows]
    if st.session_state.get(active_key) not in ids:st.session_state[active_key]=ids[0]
    main,aside=st.columns([2.1,1],gap='large')
    with main,surface(key='heatmap_panel'):
        st.subheader('各题错误人数')
        st.caption('点击小题查看作答。颜色表示判错人数，留白计错。')
        event=question_heatmap(rows,st.session_state[active_key],key='heatmap_'+batch['id'])
        token=event.get('event_id') if isinstance(event,dict) else ('legacy:'+event if isinstance(event,str) else None)
        chosen=event.get('id') if isinstance(event,dict) else event
        if token and token!=st.session_state.get('last_heat_event_'+batch['id']):
            st.session_state['last_heat_event_'+batch['id']]=token
            if chosen in ids:
                st.session_state[active_key]=chosen;st.rerun()
        active=next(r for r in rows if r['id']==st.session_state[active_key])
        st.markdown('**当前选择：第 '+safe(active['label'])+' 题**　[查看原始作答与分析证据 ↓](#question-evidence)')
        st.caption('题号角标标出尚无正误结论的人数。')
    with aside,surface(key='result_aside'):
        if view=='analysis':
            st.subheader('优先查看的题目')
            ranked=sorted([r for r in rows if r['errors']],key=lambda r:r['errors'],reverse=True)
            for r in ranked[:5]:
                st.markdown('<div class="attention-row"><b>第 '+safe(r['label'])+' 题</b><span>'+str(r['errors'])+' 人错误</span></div>',unsafe_allow_html=True)
                st.button('查看第'+r['label']+'题',key='priority_'+r['id'],width='stretch',
                    on_click=lambda qid=r['id']:st.session_state.update({active_key:qid}))
            if not ranked:st.write('目前没有判错的题目。')
        else:
            st.subheader('本次作业概况')
            for label,key in [('未判定','pending'),('留白（已计错）','not_submitted'),('无法识别','unreadable')]:
                st.markdown('<div class="overview-row"><span>'+label+'</span><b>'+str(sum(r[key] for r in rows))+'</b></div>',unsafe_allow_html=True)
            pending=next((r for r in rows if r['pending']),None)
            if pending:
                st.button('定位未判定题目',type='primary',width='stretch',on_click=lambda:st.session_state.update({active_key:pending['id']}))
            note('按题查看批改结果','选择题目和学生可抽查原卷，必要时改判。')
        if summary['average'] is None:st.caption('未提供全班核实总分，不展示平均分。')
    selected=next(r for r in rows if r['id']==st.session_state[active_key])
    with st.expander('条形图辅助视图'):
        st.bar_chart(pd.DataFrame([{'题号':r['label'],'判错人数':r['errors'],'未判定':r['pending']+r['unreadable']} for r in rows]).set_index('题号'),color=['#2563eb','#cbd5e1'])
    st.markdown('<div id="question-evidence"></div>',unsafe_allow_html=True)
    st.markdown('<div class="section-heading"><h3>第 '+safe(selected['label'])+' 题 · 作答与证据</h3>'+badge(selected['question_type'])+'</div>',unsafe_allow_html=True)
    st.caption('判错 '+str(selected['errors'])+' · 已判 '+str(selected['valid'])+' · 未判定 '+str(selected['pending'])+
               ' · 留白 '+str(selected['not_submitted'])+' · 无法识别 '+str(selected['unreadable']))
    with surface():
        subs=[s for s in rt.w['submissions'] if s['id'] in selected['submission_ids']]
        case_renderer(rt,subs,key='heat_case_'+selected['id'])
    with st.expander('补全题型与小问编号'):
        st.caption('旧记录不猜测题型。题型用于分组；修改编号不覆盖原题与分析记录。')
        frame=pd.DataFrame([{'id':q['id'],'question_no':q.get('question_no',''),'question_type':v.kind(q),
                            'parent_question_no':q.get('parent_question_no',''),'subquestion_no':q.get('subquestion_no','')} for q in batch['questions']])
        edited=st.data_editor(frame,hide_index=True,width='stretch',key='question_kinds_'+batch['id'],disabled=['id'],
            column_config={'id':None,'question_no':'题号','question_type':st.column_config.SelectboxColumn('题型',options=['未分类']+v.TYPES),
                'parent_question_no':'大题号','subquestion_no':'小问号'})
        if st.button('保存题型与小问编号',key='save_kinds_'+batch['id']):
            try:v.update_types(rt.w,batch['id'],edited.fillna('').to_dict('records'));rt.persist();st.rerun()
            except ValueError as exc:st.error(str(exc))
    with st.expander('录入已核实的总分（可选）'):
        st.caption('只使用教师核实的总分；不由AI编造。全体已提交学生均有可靠总分时才展示平均分。')
        students=sorted({s['student_id'] for s in rt.w['submissions'] if s['id'] in batch['submission_ids'] and s.get('submission_status')!='not_submitted'})
        maximum=st.number_input('本次满分',min_value=1.0,value=float(batch.get('verified_scores',{}).get('max_score',100)),key='score_max_'+batch['id'])
        existing=batch.get('verified_scores',{}).get('values',{})
        scores=st.data_editor(pd.DataFrame([{'匿名编号':sid,'总分':existing.get(sid)} for sid in students]),disabled=['匿名编号'],hide_index=True,key='scores_'+batch['id'])
        confirmed=st.checkbox('这些总分已由教师核实',key='score_checked_'+batch['id'])
        if st.button('保存已核实总分',disabled=not confirmed,key='save_scores_'+batch['id']):
            try:
                values={r['匿名编号']:float(r['总分']) for r in scores.to_dict('records') if pd.notna(r['总分'])}
                v.save_scores(rt.w,batch['id'],values,float(maximum));rt.persist();st.rerun()
            except (ValueError,TypeError) as exc:st.error(str(exc))

