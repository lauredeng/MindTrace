"""Confirmed-results page: question heatmap is the primary exam visualization."""
import pandas as pd
import streamlit as st
from core import presentation as v,product as p
from ui.experience import surface,badge,safe
from ui.heatmap import question_heatmap

def focus_question(active_key,question_id,filter_value):
    st.session_state[active_key]=question_id
    st.session_state['heat_case_'+question_id+'_filter']=filter_value


def results(rt,batch,case_renderer,view='grading'):
    from ui.design import page_header,metric
    execution=p.batch_execution(rt.w,batch['id'])
    if execution['status']=='ready' and not any(p.current_records(s,'analyses') for s in rt.w['submissions'] if s['id'] in batch['submission_ids']):
        page_header(batch['name'] if view=='grading' else '班级错误分析',
                    f'已保存 {execution["total"]} 份逐题作答。','作业批改','待批改')
        st.info('识别和校对已完成。'+('点击「开始批改」，完成后即可查看班级统计。' if view=='grading'
                                else '请先到「作业批改」开始批改。'))
        return
    rows=v.heatmap_rows(rt.w,batch['id'],automatic=True)
    summary=v.batch_summary(rt.w,batch['id'],automatic=True,rows=rows)
    page_header(batch['name'] if view=='grading' else '班级错误分析',
        '点击题号查看学生作答和批改依据。',
        '作业批改 / 批改结果' if view=='grading' else batch['name'],summary['status'])
    execution=summary['execution']
    progress_text=f"已处理 {execution['complete']} / {execution['total']} 份作答。"
    if execution['status']=='failed':
        retry='点击「重试未完成的批改」。' if view=='grading' else '回到「作业批改」重试。'
        st.error('本次未生成有效批改结果。'+retry)
    elif execution['status']=='partial':
        st.warning(progress_text+' 其余作答可重试或核对原卷。')
    elif execution['status']=='paused':
        reason=batch.get('pause_reason','请求受到限制，请稍后继续。')
        st.warning(progress_text+' '+reason+' 进度已保存。')
    if execution['needs_transcription']:
        st.info(f'{execution["needs_transcription"]} 份作答的识别文字不完整。可在作答详情的「原卷与校对」中处理。')
    cards=st.columns(4,gap='large')
    with cards[0]:metric('提交学生',summary['submitted_students'],'同一学生提交多题仅计一人',accent=True,icon_name='people')
    with cards[1]:metric('平均正确率',f"{summary['correctness']:.1%}" if summary['correctness'] is not None else '—',
        f"正确 {summary['correct_count']} / 已判 {summary['valid_count']}",icon_name='chart')
    waiting=sum(r['waiting'] for r in rows)
    with cards[2]:metric('批改异常',sum(r['pending']+r['unreadable'] for r in rows)-waiting,
                         f'另有 {waiting} 条尚待批改' if waiting else '未能形成正误结论',icon_name='review')
    with cards[3]:metric('判错作答',sum(r['errors'] for r in rows),'包含卷面已确认的留白',icon_name='check')
    if summary['correctness'] is None:
        st.info('尚未得到正误结果，正确率显示“—”。')
    elif any(r['pending'] or r['unreadable'] for r in rows):
        st.caption('正确率只计入已判正误的作答，确认留白按错计入。')
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
        st.caption('颜色表示判错人数，右上角数字表示尚无正误结论的人数。')
        event=question_heatmap(rows,st.session_state[active_key],key='heatmap_'+batch['id'])
        token=event.get('event_id') if isinstance(event,dict) else ('legacy:'+event if isinstance(event,str) else None)
        chosen=event.get('id') if isinstance(event,dict) else event
        if token and token!=st.session_state.get('last_heat_event_'+batch['id']):
            st.session_state['last_heat_event_'+batch['id']]=token
            if chosen in ids:
                st.session_state[active_key]=chosen;st.rerun()
        active=next(r for r in rows if r['id']==st.session_state[active_key])
        st.markdown('**当前选择：第 '+safe(active['label'])+' 题**　[查看原始作答与分析证据 ↓](#question-evidence)')
    with aside,surface(key='result_aside'):
        if view=='analysis':
            st.subheader('优先查看的题目')
            ranked=sorted([r for r in rows if r['errors']],key=lambda r:r['errors'],reverse=True)
            for r in ranked[:5]:
                st.markdown('<div class="attention-row"><b>第 '+safe(r['label'])+' 题</b><span>'+str(r['errors'])+' 人错误</span></div>',unsafe_allow_html=True)
                st.button('查看第'+r['label']+'题',key='priority_'+r['id'],width='stretch',
                    on_click=focus_question,args=(active_key,r['id'],'错误'))
            if not ranked:st.write('目前没有判错的题目。')
        else:
            st.subheader('本次作业概况')
            overview=[('待批改',waiting),('批改后未判定',sum(r['pending'] for r in rows)-waiting),
                      ('留白（已计错）',sum(r['not_submitted'] for r in rows)),('无法识别',sum(r['unreadable'] for r in rows))]
            for label,count in overview:
                st.markdown('<div class="overview-row"><span>'+label+'</span><b>'+str(count)+'</b></div>',unsafe_allow_html=True)
            wrong=next((r for r in rows if r['errors']),None)
            if wrong:
                st.button('定位错误作答',width='stretch',on_click=focus_question,args=(active_key,wrong['id'],'错误'))
            uncertain=next((r for r in rows if r['pending']>r['waiting'] or r['unreadable']),None)
            if uncertain:
                st.button('定位异常作答',width='stretch',on_click=focus_question,args=(active_key,uncertain['id'],'异常'))
        with st.popover('批次设置'):
            batch_settings(rt,batch)
        bars=st.toggle('查看条形图',key='show_bars_'+batch['id'])
    selected=next(r for r in rows if r['id']==st.session_state[active_key])
    if bars:
        st.bar_chart(pd.DataFrame([{'题号':r['label'],'判错人数':r['errors'],'未判定':r['pending']+r['unreadable']} for r in rows]).set_index('题号'),color=['#2563eb','#cbd5e1'])
    st.markdown('<div id="question-evidence"></div>',unsafe_allow_html=True)
    st.markdown('<div class="section-heading"><h3>第 '+safe(selected['label'])+' 题 · 作答与证据</h3>'+badge(selected['question_type'])+'</div>',unsafe_allow_html=True)
    st.caption('判错 '+str(selected['errors'])+' · 已判 '+str(selected['valid'])+' · 未判定 '+str(selected['pending'])+
               ' · 留白 '+str(selected['not_submitted'])+' · 无法识别 '+str(selected['unreadable']))
    with surface():
        subs=[s for s in rt.w['submissions'] if s['id'] in selected['submission_ids']]
        case_renderer(rt,subs,key='heat_case_'+selected['id'])


def batch_settings(rt,batch):
    section=st.segmented_control('批次设置项目',['题号与题型','班级总分'],default='题号与题型',
                                 required=True,key='batch_settings_'+batch['id'])
    if section=='题号与题型':
        st.caption('修改后会更新题目分组，原题与批改记录会保留。')
        frame=pd.DataFrame([{'id':q['id'],'question_no':q.get('question_no',''),'question_type':v.kind(q),
                            'parent_question_no':q.get('parent_question_no',''),'subquestion_no':q.get('subquestion_no','')} for q in batch['questions']])
        edited=st.data_editor(frame,hide_index=True,width='stretch',key='question_kinds_'+batch['id'],disabled=['id'],
            column_config={'id':None,'question_no':'题号','question_type':st.column_config.SelectboxColumn('题型',options=['未分类']+v.TYPES),
                'parent_question_no':'大题号','subquestion_no':'小问号'})
        if st.button('保存题型与小问编号',key='save_kinds_'+batch['id']):
            try:v.update_types(rt.w,batch['id'],edited.fillna('').to_dict('records'));rt.persist();st.rerun()
            except ValueError as exc:st.error(str(exc))
    else:
        st.caption('录入所有已交作业学生的总分后，页面会显示班级平均分。')
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

