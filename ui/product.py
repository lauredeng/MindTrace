"""V1.2 streamlined teacher and student product surfaces."""
from datetime import date
from collections import Counter
import io
import json
import pandas as pd
import streamlit as st
from core import product as p, education as e, classroom as c, presentation as v
from core.collaboration import has_student_number
from core.limits import auto_resume, UsageLimitError
from ui.workbench import Runtime,image_input,manual_form,source_panel,message,dumps
from ui.experience import card,surface,empty,badge,topic_chips,go,safe
from ui.design import BRAND_TITLE

LABEL={'correct':'正确','incorrect':'错误','uncertain':'未判定'}

def batch_picker(rt):
    batches=rt.w['batches']
    if not batches:return None
    focus=st.session_state.pop('v12_batch_pending',None)
    ids=[b['id'] for b in batches]
    if focus in ids:
        st.session_state['v12_batch']=focus
    bid=st.selectbox('查看作业批次',ids,index=len(ids)-1,key='v12_batch',
        format_func=lambda k:next(b['name']+' · '+str(len(b['submission_ids']))+' 份作答' for b in batches if b['id']==k))
    return next(b for b in batches if b['id']==bid)

def save_batch(rt,name,rows,source,materials=None):
    batch=p.create_batch(rt.w,name,rows,source,grading_policy=p.CLASSROOM_POLICY,materials=materials)
    st.session_state['v12_batch_pending']=batch['id']
    st.session_state['show_assignment_upload']=False
    rt.persist()
    return [s for s in rt.w['submissions'] if s['id'] in batch['submission_ids']]

def upload_assignment(rt):
    from ui.assignment_upload import teacher_upload
    from core.uploads import reject_existing
    name=st.text_input('本次作业名称',value='数学作业 '+date.today().isoformat(),max_chars=100,key='v12_batch_name')

    def save(rows,materials,sources,evidence):
        e.text(name,100,'作业名称')
        reject_existing(rt.w,name,materials)
        if len(rows)>p.BATCH_LIMIT:
            raise ValueError(f'本批识别结果超过 {p.BATCH_LIMIT} 条作答，请分成两份作业批次。')
        existing={}
        for sub in rt.w['submissions']:
            known=sub['student_id']
            existing.setdefault(known.upper(),set()).add(known)
        for material in materials:
            student=material['student_id']
            matches=existing.get(student,set())
            if len(matches)>1:
                raise ValueError(f'编号 {student} 在已有记录中对应多个写法，请先核对课堂记录。')
            if matches:
                material['student_id']=next(iter(matches))
                for row in rows:
                    if row['student_id']==student:row['student_id']=material['student_id']
        for row in rows:e.normalize_submission(row,allow_unanswered=True)
        if materials[0]['kind']=='pdf':
            for ref,data in sources.items():rt.upload_evidence(ref,original=True,data=data)
        for ref,data in evidence.items():rt.upload_evidence(ref,data=data)
        save_batch(rt,name,rows,'image_confirmed',materials)

    pdf,photos=st.tabs(['全班作业 · PDF','单名学生 · 图片'])
    with pdf:teacher_upload(rt,'pdf',save)
    with photos:teacher_upload(rt,'photos',save)
    from core.settings import developer_enabled
    if developer_enabled():
        with st.expander('体验匿名构造材料'):
            st.caption('只导入原始材料，没有预设诊断；点击批改才调用真实模型。')
            if st.button('载入跨章节原始材料'):
                rows=json.loads((rt.root/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
                save_batch(rt,'跨章节构造材料',rows,'constructed_examples');st.rerun()


def legacy_assignment_import(rt):
    with st.expander('兼容导入 · CSV 和手动补录'):
        name=st.text_input('兼容导入作业名称',value='数学作业 '+date.today().isoformat(),max_chars=100,key='legacy_import_name')
        csv,text=st.tabs(['电子作业','手动补充'])
        with csv:
            file=st.file_uploader('导入电子作业 CSV',type=['csv'],key='v12_csv')
            st.caption('需要 student_id、question、steps 或 answer；保留旧 student_answer 求导格式。')
            if file:
                try:
                    if file.size>1024*1024:raise ValueError('CSV最多1MB。')
                    frame=pd.read_csv(io.BytesIO(file.getvalue()),dtype=str,keep_default_na=False,encoding='utf-8-sig')
                    rows=frame.to_dict('records')
                    if not 1<=len(rows)<=p.BATCH_LIMIT:raise ValueError(f'每批1–{p.BATCH_LIMIT}条。')
                    for row in rows:
                        if 'student_answer' in row and 'steps' not in row:
                            row.update(answer=row['student_answer'],task_type='derivative',tool_expression=row['question'])
                        e.normalize_submission(row,allow_unanswered=True)
                    st.dataframe(frame.head(8),hide_index=True,width='stretch')
                    if st.button('确认电子作业导入',type='primary'):
                        save_batch(rt,name,rows,'csv');go('教师工作空间','作业批改');st.rerun()
                except (ValueError,UnicodeError,KeyError) as exc:st.error(str(exc))
        with text:
            row=manual_form('v12_teacher_text')
            if row:
                try:
                    save_batch(rt,name,[row],'manual');go('教师工作空间','作业批改');st.rerun()
                except ValueError as exc:st.error(str(exc))


def reference_panel(rt,batch):
    groups,_=p.reference_catalog(rt.w,batch)
    if not groups:return
    keys=batch.get('answer_keys',{})
    confirmed=sum(bool(keys.get(key,{}).get('confirmed')) for key in groups)
    drafts=sum(bool(keys.get(key,{}).get('draft') and not keys[key].get('confirmed')) for key in groups)
    with st.expander(f'本次作业的参考答案 · 已确认 {confirmed} / {len(groups)}',expanded=bool(drafts)):
        st.caption('填写已有答案，或先生成 AI 草稿，核对后再保存。全班同一题共用一份参考答案；未填写的题由 AI 逐份批改。')
        missing=any(not (keys.get(key,{}).get('confirmed') or keys.get(key,{}).get('draft')) and not p.unreadable(sub)
                    for key,sub in groups.items())
        if st.button('为缺少答案的题生成 AI 草稿',key='draft_keys_'+batch['id'],
                     disabled=not rt.ready() or not missing):
            progress=st.empty()
            wait=st.empty()
            call=auto_resume(rt.call,lambda _,seconds:show_wait(wait,seconds,'生成参考答案'))
            try:
                with st.spinner('正在为全班准备共用参考答案…',show_time=True):
                    notice=p.generate_references(rt.w,batch['id'],call,
                        lambda i,n:progress.info(f'准备第 {i} / {n} 道题的参考答案'),
                        prepare=rt.prepare_workspace,persist=rt.persist)
            except RuntimeError as exc:
                st.warning(str(exc))
            else:
                st.session_state['reference_notice_'+batch['id']]=notice
                st.rerun()
        notice=st.session_state.pop('reference_notice_'+batch['id'],'')
        if notice:st.info(notice)
        rows=[]
        for key,sub in sorted(groups.items(),key=lambda item:v.sort_key({'label':v.hierarchy(item[1])[2]})):
            entry=keys.get(key,{})
            confirmed_key=entry.get('confirmed')
            candidate=confirmed_key or entry.get('draft') or {}
            rows.append({'id':key,'题号':v.hierarchy(sub)[2],'题型':sub['question_type'],'题干':sub['question'],
                         '参考答案':candidate.get('answer',''),'评分依据':candidate.get('rubric',''),
                         '采用草稿':False,'来源 / 状态':{'ai_draft':'待核对的 AI 草稿','ai_confirmed':'教师已核对 AI 草稿',
                          'teacher':'教师录入'}.get(candidate.get('source'),entry.get('error','待填写'))})
        expected=p.digest(keys)
        with st.form('answer_keys_'+batch['id']+expected[:12]+p.digest(list(groups))[:12]):
            edited=st.data_editor(pd.DataFrame(rows).set_index('id'),hide_index=True,width='stretch',
                disabled=['题号','题型','题干','来源 / 状态'],column_config={
                    '题干':st.column_config.TextColumn(width='large'),
                    '参考答案':st.column_config.TextColumn(width='medium',max_chars=2000),
                    '评分依据':st.column_config.TextColumn(width='medium',max_chars=2000),
                    '采用草稿':st.column_config.CheckboxColumn(help='保持 AI 草稿原文时勾选；手工填写或修改后可直接保存。')})
            confirm_all=st.checkbox('我已核对，采用表内全部未修改的 AI 草稿') if drafts else False
            submitted=st.form_submit_button('保存并确认参考答案')
        if submitted:
            changes={}
            for key,row in edited.fillna('').iterrows():
                values=(row['参考答案'].strip(),row['评分依据'].strip())
                entry=keys.get(key,{})
                draft=entry.get('draft')
                if (not entry.get('confirmed') and draft and values==(draft['answer'],draft['rubric'])
                        and not (confirm_all or row['采用草稿'])):
                    continue
                changes[key]=values
            try:
                count=p.save_references(rt.w,batch['id'],changes,expected,
                                        prepare=rt.prepare_workspace,persist=rt.persist)
            except (RuntimeError,ValueError) as exc:
                st.warning(str(exc))
            else:
                if count:
                    st.session_state['reference_notice_'+batch['id']]=f'已确认 {count} 道题的参考答案。已有批改时，只需重跑受影响的题目。'
                    st.rerun()
                st.info('本次没有新的参考答案需要确认。')


def show_wait(place,seconds,action):
    if seconds:
        place.info(f'AI 服务短暂限流或繁忙。约 {seconds} 秒后自动继续{action}，已完成内容会保留。')
    else:
        place.empty()


def roster_panel(rt):
    from core.uploads import parse_roster
    roster=rt.w.get('student_roster',[])
    with st.popover(f'班级学号名单 · {len(roster)} 人',width='stretch'):
        st.caption('每行一个学号。以后上传「学号.pdf」即可自动匹配。')
        with st.form('class_roster_'+rt.w['id']+p.digest(roster)[:10]):
            value=st.text_area('班级学号名单',value='\n'.join(roster),max_chars=33000,height=125)
            save=st.form_submit_button('保存班级名单')
        if save:
            try:
                numbers=parse_roster(value)
                if numbers!=roster:
                    c.commit(rt.w,'roster-'+c.uid(),lambda w:w.update(student_roster=numbers))
                    rt.persist()
                    st.rerun()
            except ValueError as exc:st.error(str(exc))


def teacher(rt):
    from ui.design import page_header
    toolbar=st.columns([1.25,1.25,1.7,3])
    with toolbar[0].popover('切换作业',width='stretch'):
        batch=batch_picker(rt)
    with toolbar[2]:
        roster_panel(rt)
    if batch:
        if toolbar[1].button('上传新作业',width='stretch'):
            st.session_state['show_assignment_upload']=not st.session_state.get('show_assignment_upload',False)
    else:
        page_header('上传作业','上传全班 PDF 或一名学生的照片。识别后先核对，再开始批改。','教师工作台 / 作业批改')
    if not batch or st.session_state.get('show_assignment_upload',False):
        with surface(key='upload_assignment'):
            upload_assignment(rt)
    if not batch:return
    reference_panel(rt,batch)
    execution=p.batch_execution(rt.w,batch['id'])
    can_grade=rt.ready() or any(entry.get('confirmed') for entry in batch.get('answer_keys',{}).values())
    def execute_batch():
        progress=st.progress(0,text='准备批改，已成功结果将复用…')
        waiting=st.empty()
        def provider(*args,**kwargs):
            if not rt.ready():
                raise UsageLimitError('AI 服务尚未启用，剩余需要 AI 的作答已保留。',reason='service')
            return rt.call(*args,**kwargs)
        call=auto_resume(provider,lambda _,seconds:show_wait(waiting,seconds,'批改'))
        def update(stage,i,n):
            rt.persist()
            progress.progress((0 if stage=='quick' else .5)+.5*i/n,text=('快速批改' if stage=='quick' else '疑难作答核验')+f' {i}/{n}')
        try:
            p.run_batch(rt.w,batch['id'],call,update,_prepare=rt.prepare_workspace,_persist=rt.persist)
        except RuntimeError:
            st.warning('暂时无法继续批改。如果另一窗口正在处理，请稍后刷新查看进度。')
            return
        st.rerun()
    if execution['status'] in ('failed','partial','paused') or (batch.get('status')=='running' and execution['remaining']):
        action='继续未完成的批改' if execution['status']=='paused' or batch.get('status')=='running' else '重试未完成的批改'
        if st.button(action,type='primary',disabled=not can_grade or not execution['retryable_remaining'],
                     key='retry_batch_'+batch['id']):execute_batch()
        st.caption('继续批改时会保留已有判定。')
    elif execution['status']=='ready':
        if st.button('开始批改',type='primary',disabled=not can_grade,key='start_batch_'+batch['id']):
            execute_batch()
        if not rt.ready():st.warning('AI 服务尚未启用，配置服务后即可开始批改。')
    from ui.results import results
    results(rt,batch,selected_case,view='grading')


def question_table(rows):
    st.dataframe([{'题号':g['label'],'题目':g['question'][:100],'已判':g['valid'],
        '正确':g['correct'],'错误':g['errors'],'留白（已计错）':g['not_submitted'],
        '待批改':g['waiting'],'批改后未判定':g['pending']-g['waiting'],
        '无法识别':g['unreadable']} for g in rows],hide_index=True,width='stretch')

def transcription_editor(rt,sub,state,key):
    if not sub.get('batch_id') or not sub.get('image_ref'):
        return
    first=state['first_error_step']
    if first and 1<=first<=len(sub['steps']):
        st.warning(f'请先对照原图核对第 {first} 行，再确认该处是否为学生错误。')
        st.text(sub['steps'][first-1])
    st.subheader('校对识别文字')
    if not rt.image(sub['image_ref']):
        st.info('原图暂不可用，无法对照校正。')
        return
    st.caption('对照原图校正题干、选项或作答。原图及历史记录会保留。')
    form_key=key+'_transcription_'+sub['id']+'_'+sub['fingerprint']
    with st.form(form_key):
        question=st.text_area('题干与选项',value=sub['question'],max_chars=4000)
        steps=st.text_area('作答步骤（每行一步）',value='\n'.join(sub['steps']),max_chars=8000)
        answer=st.text_input('作答的最终答案',value=sub['answer'],max_chars=2000)
        checked=st.checkbox('我已对照原图确认转写')
        submit=st.form_submit_button('保存转写并重判本题',disabled=not rt.ready())
    if submit:
        if not checked:
            st.warning('请先对照原图确认转写。')
            return
        try:
            with st.spinner('正在重新批改这一题…'):
                p.regrade_transcription(rt.w,sub['batch_id'],sub['id'],sub['fingerprint'],steps,answer,rt.call,
                                        question=question,prepare=rt.prepare_workspace,persist=rt.persist)
            st.rerun()
        except (OSError,RuntimeError,ValueError) as exc:
            st.warning(str(exc))


def selected_case(rt,subs,key='v12_case'):
    if not subs:return
    groups={'全部':subs,'异常':[],'错误':[],'正确':[]}
    classifications={'pending':'异常','unreadable':'异常','not_submitted':'错误',
                     'incorrect':'错误','correct':'正确'}
    record_states={sub['id']:v.record_state(rt.w,sub,automatic=True) for sub in subs}
    for sub in subs:
        status=record_states[sub['id']]
        group='待批改' if v.waiting_for_grade(sub,status) else classifications[status]
        groups.setdefault(group,[]).append(sub)
    filter_key=key+'_filter'
    filter_value=st.segmented_control('本题作答',list(groups),
        default=None if filter_key in st.session_state else '全部',required=True,key=filter_key,
        format_func=lambda label:f'{label} {len(groups[label])}')
    selected=groups[filter_value]
    if not selected:
        st.caption(f'本题没有{filter_value}作答。可选「全部」，或在上方切换题号。')
        return
    ids=[s['id'] for s in selected]
    focus=st.session_state.pop('v12_case_pending',None)
    if focus in ids:st.session_state[key]=focus
    elif st.session_state.get(key) not in ids:st.session_state[key]=ids[0]
    filenames={m['student_id']:m['pages'][0]['filename'] for b in rt.w['batches'] for m in b.get('materials',[])
               if m['identity_status']=='file_group'}
    labels={s['id']:filenames.get(s['student_id'],s['student_id'])+' / '+(s['question_no'] or s['topic']) for s in selected}
    sid=st.selectbox('查看学生原始作答',ids,key=key,format_func=labels.get)
    sub=next(s for s in selected if s['id']==sid)
    state=p.effective(rt.w,sub)
    review_tab,original_tab,feedback_tab=st.tabs(['作答与批改','原卷与校对','学生反馈'])
    with review_tab:
        a,b=st.columns([1,1.15],gap='large')
    with a:
        st.subheader('原始题目与作答')
        source_panel(rt,sub,show_student=sub['student_id'] not in filenames,show_transcription=False)
    with b:
        st.subheader('批改依据')
        record_status=record_states[sub['id']]
        label={'unreadable':'识别不完整','not_submitted':'留白 · 已计错','pending':'未得到判定',
               'correct':'正确','incorrect':'错误'}[record_status]
        if v.waiting_for_grade(sub,record_status):label='待批改'
        st.markdown(badge(label)+(badge('教师判定') if state['confirmed'] else ''),unsafe_allow_html=True)
        st.write(state['basis'])
        failed=False
        for key_name in ('quick_checks','analyses'):
            records=p.current_records(sub,key_name)
            if records and records[-1]['status']=='failed':
                failed=True
                st.error('最近一次未完成：'+records[-1]['error'])
        if p.unreadable(sub):
            st.warning('识别文字不完整。切换到「原卷与校对」，对照原卷补全题干或作答。')
        elif failed and sub.get('batch_id') and st.button('重试本题批改',key=key+'_retry_'+sub['id'],disabled=not rt.ready()):
            try:
                with st.spinner('正在重试这一题的未完成步骤…'):
                    p.run_batch(rt.w,sub['batch_id'],rt.call,lambda *_:rt.persist(),
                                _prepare=rt.prepare_workspace,_persist=rt.persist,submission_id=sub['id'])
                st.rerun()
            except (OSError,RuntimeError,ValueError) as exc:
                st.warning(str(exc))
        quick=p.latest(sub,'quick_checks')
        if quick:
            label='识别出的学生答案' if quick.get('evidence_id')=='ANSWER' else (
                '原题依据' if quick.get('evidence_id')=='QUESTION' or quick.get('blank') else '判定引用的原始作答')
            st.text(label+'：'+quick['evidence_quote'])
        if not state['confirmed'] and p.latest(sub,'quick_checks') and state['verdict']!='uncertain' and v.record_state(rt.w,sub) not in ('unreadable','not_submitted'):
            if st.button('确认这份批改',key=key+'_confirm_'+sub['id']):
                try:v.confirm_short(rt.w,sub['id']);rt.persist();st.rerun()
                except ValueError as exc:st.error(str(exc))
        if not p.is_blank(sub):
            with st.popover('教师改判'):
                previous=c.latest_review(rt.w,sub['id'])
                with st.form(key+'_override_'+sub['id']+'_'+sub['fingerprint']):
                    verdict=st.selectbox('批改结论',['correct','incorrect'],
                                         index=['correct','incorrect'].index(state['verdict']) if state['verdict']!='uncertain' else None,
                                         format_func=lambda value:LABEL[value])
                    note=st.text_area('教师备注 / 修改依据',value=(previous or {}).get('note',''),max_chars=2000)
                    submit=st.form_submit_button('保存复核并更新统计')
                if submit:
                    try:
                        v.override_grade(rt.w,sub['id'],verdict,note);rt.persist();st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

    with original_tab:
        source,editor=st.columns([1,1],gap='large')
        with source:
            upload_provenance(rt,sub,key)
        with editor:
            if sub.get('batch_id') and sub.get('image_ref'):
                transcription_editor(rt,sub,state,key)
            else:
                st.caption('这份作答没有可校对的上传图片。')

    with feedback_tab:
        entries=[n for n in rt.w['notebook'] if n['student_id']==sub['student_id'] and p.item_key(sub)==n.get('question_id') and not n.get('deleted')]
        sessions=[t for t in rt.w['study_sessions'] if t['submission_id']==sub['id'] and t['student_id']==sub['student_id']]
        if entries:
            item=entries[0]
            st.write('学生当前错因：'+item['primary_category']+' · '+('本人已确认' if item['category_confirmed'] else '待本人确认'))
            if item['notes']:st.write('学生备注：'+item['notes'])
        turns=[t for session in sessions for t in session['turns']]
        st.write('本题辅导互动：'+str(len(turns))+' 次')
        if turns:
            latest=turns[-1]
            if latest.get('reply'):st.write('最近追问：'+latest['reply'])
            st.caption('最近学习问题：'+latest.get('purpose',''))
        if not entries and not turns:st.caption('学生尚未收录或留下本题学习反馈。')
        from core import agent as tutoring_agent
        runs=[r for record in sessions for r in record.get('agent_runs',[])]
        if runs:
            latest_run=runs[-1]
            st.write('深度辅导状态：'+tutoring_agent.STATUSES.get(latest_run['status'],'已记录'))
            review=c.latest_review(rt.w,sub['id'])
            pending=[r for r in runs if r.get('needs_teacher_review') and (not review or review['created_at']<r['requested_at'])]
            if pending:st.warning('本题已请求教师核对，请结合原始证据复核。')
            with st.popover('查看辅导过程'):
                for trace in latest_run['trace']:
                    if trace.get('policy')=='allowed':
                        st.write(tutoring_agent.ACTIONS[trace['action']]+'：'+trace['rationale'])
                        st.caption('证据引用：'+'、'.join(trace['evidence_ids']))
                    elif trace.get('observation'):st.caption('未执行动作：'+trace['observation'].get('reason','不满足条件'))
                verified=next((r['practice'] for r in reversed(runs) if r.get('practice',{}).get('attempts')),None)
                if verified:st.write('新题验证：'+e.learning_state(verified['attempts']))

def insights(rt):
    from ui.design import page_header
    with st.popover('选择分析的作业'):
        batch=batch_picker(rt)
    if not batch:
        page_header('班级错误分析','从每道题，回到可核对的原始证据。','教师工作台')
        empty('还没有可分析的作业','上传作业并完成批改后，在这里定位共性问题。')
        st.button('上传并批改作业',type='primary',on_click=go,args=('教师工作空间','作业批改'));return
    from ui.results import results
    results(rt,batch,selected_case,view='analysis')


def upload_provenance(rt,sub,key):
    batch=next((b for b in rt.w['batches'] if b['id']==sub.get('batch_id')),None)
    material=next((m for m in (batch or {}).get('materials',[]) if m['student_id']==sub['student_id']),None)
    if not material:
        image=rt.image(sub.get('image_ref')) if sub.get('image_ref') else None
        if image:st.image(image,width=450)
        else:st.caption('这份作答没有可查看的原卷。')
        if sub.get('transcription'):st.text(sub['transcription'])
        return
    pages=material['pages']
    st.caption('本题来源页 · '+'、'.join(map(str,sub['source_pages'])))
    st.subheader('原卷')
    selected=st.selectbox('作业页码',range(1,len(pages)+1),index=sub['source_pages'][0]-1,
                          key=key+'_evidence_page_'+sub['id'])
    page=pages[selected-1]
    st.caption(page['filename']+' · 第 '+str(selected)+' 页')
    image=rt.image(page['original_image'])
    if image:st.image(image,width=450)
    if page['transcription']:st.text(page['transcription'])
    if page.get('recognized_records'):
        st.caption('该页初次识别结果')
        for record in page['recognized_records']:
            st.text('\n'.join([record['question'],*record['steps'],record['answer']]).strip())
    if page.get('recognized_answers'):
        st.caption('该页独立作答')
        for answer in page['recognized_answers']:
            st.text('\n'.join([answer['question_no'],*answer['steps'],answer['answer']]).strip())
    original=rt.upload_evidence(page['original_file'],original=material['kind']=='pdf')
    if original:
        st.download_button('下载原始文件',original,file_name=page['filename'],on_click='ignore',
                           key=key+'_original_'+sub['id'])
    else:st.info('原始文件当前不可用，请查阅教师留存的原件。')


def history(rt):
    from ui.design import page_header
    page_header('历史记录','选择一次作业，查看学生原卷、批改结果与教师复核。')
    batch=batch_picker(rt)
    if not batch:
        empty('还没有作业记录','保存一份作业后，就可以在这里查看。')
        st.button('上传作业',type='primary',on_click=go,args=('教师工作空间','作业批改'))
        return
    rows=v.heatmap_rows(rt.w,batch['id'],automatic=True);question_table(rows)
    subs=[s for s in rt.w['submissions'] if s['id'] in batch['submission_ids']]
    export=[{'匿名编号':s['student_id'],'题号':s['question_no'],'题目':s['question'],
        '判断':{'not_submitted':'错误','unreadable':'无法识别','pending':'未判定',**LABEL}[v.record_state(rt.w,s,automatic=True)],'教师确认':p.effective(rt.w,s)['confirmed'],
        '依据':p.effective(rt.w,s)['basis']} for s in subs]
    def csv_safe(v):
        return "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v
    frame=pd.DataFrame(export).apply(lambda column:column.map(csv_safe))
    st.download_button('导出本批批改结果',frame.to_csv(index=False).encode('utf-8-sig'),'mindtrace_results.csv','text/csv')
    selected_case(rt,subs,key='history_case')

def student_id(rt):
    if rt.assigned_student:
        sid=rt.assigned_student
    else:
        from uuid import uuid4
        choice=st.session_state.get('studio_student_choice')
        if choice and choice[0]==rt.w['id'] and has_student_number(rt.w,choice[1]):
            sid=choice[1]
        else:
            guest=st.session_state.get('studio_guest_student')
            if not guest or guest[0]!=rt.w['id']:
                guest=(rt.w['id'],'STU-'+uuid4().hex[:10])
                st.session_state['studio_guest_student']=guest
            sid=guest[1]
    st.session_state['studio_current_student']=sid
    return sid


def student_identity_panel(rt):
    if rt.assigned_student:return
    if rt.access:return
    from ui.collaboration import demo_student_form
    classroom=st.query_params.get('class')
    choice=st.session_state.get('studio_student_choice')
    selected=choice and choice[0]==rt.w['id'] and has_student_number(rt.w,choice[1])
    if selected:
        st.caption('演示学号 · '+choice[1])
        if st.button('退出学号，返回自主学习'):
            st.session_state.pop('studio_student_choice',None)
            st.session_state.pop('v12_sub',None)
            st.session_state.pop('v12_sub_pending',None)
            st.rerun()
    else:
        with st.expander('按学号查看教师作业',expanded=bool(classroom)):
            st.caption('用老师分享的演示链接进入，再输入学号。只想拍题时，可以直接上传。')
            demo_student_form(rt.w,classroom)


def show_correction(correction):
    st.markdown('**参考解答**')
    message(correction['answer'] or '本次先给思路，未展开最终答案。')
    for i,row in enumerate(correction['steps'],1):
        message('**'+str(i)+'.** '+row['text'])
        st.caption('依据：'+row['reason'])
    for item in correction['supplements']:
        with st.container(border=True):
            message(item['content'])
            st.caption('适用条件：'+item['conditions'])
            st.write('与本题的关系：'+item['connection'])
    st.caption({'partial':'部分步骤已有数学核验。','checked':'已完成可用的数学核验。'}.get(correction['reference_tool']['status'],'请结合原题条件核对参考解。')+' AI解答仍可能出错。')
    for warning in correction['uncertainties']:st.warning(warning)

def student_composer(rt,sid):
    key='v12_ask_'+rt.w['id']+'_'+sid
    pending_question=key+'_pending_question'
    pending_upload=key+'_pending_upload'
    with st.container(key='student_composer'):
        sent=st.chat_input('输入数学题，或描述你卡在哪一步',key=key,max_chars=2000,
                           accept_file='multiple',file_type=['pdf','png','jpg','jpeg','webp'])
        st.caption('可直接发文字，也可附上图片或 PDF。每次最多 5 个附件、合计 12 页。')
        if sent:
            question=sent.text.strip()
            if sent.files:
                st.session_state[pending_upload]=(sent.files,question)
            elif question:
                sub=rt.add({'student_id':sid,'question':question},'self_study',allow_unanswered=True)
                st.session_state['v12_sub_pending']=sub['id']
                st.session_state[pending_question]={'text':question,'ids':[sub['id']]}
                if rt.ready():
                    try:
                        with st.spinner('正在回答…'):
                            p.study_turn(rt.w,sub,'reply',question,rt.call)
                    except (RuntimeError,ValueError) as exc:
                        st.session_state[key+'_notice']=str(exc)
                    else:
                        st.session_state.pop(pending_question,None)
                        rt.persist()
                st.rerun()
        notice=st.session_state.pop(key+'_notice',None)
        if notice:st.warning(notice)
        attached=st.session_state.get(pending_upload)
        if attached:
            files,question=attached
            if st.button('移除本次附件',key=key+'_remove'):
                st.session_state.pop(pending_upload,None)
                st.rerun()
            if question:
                st.caption('附带的问题会在核对题目后带入答疑。')
                st.text(question)
            saved=image_input(rt,key+'_attachments',True,allow_unanswered=True,student_id=sid,files=files)
            if saved:
                st.session_state.pop(pending_upload,None)
                st.session_state['v12_sub_pending']=saved[0]['id']
                if question:
                    st.session_state[pending_question]={'text':question,'ids':[sub['id'] for sub in saved]}
                st.rerun()
        with st.popover('填写详细题目'):
            row=manual_form('v12_student_text',student_id=sid,hide_student=True)
            if row:
                try:
                    sub=rt.add(row,'self_study',allow_unanswered=True)
                    st.session_state['v12_sub_pending']=sub['id']
                    st.rerun()
                except ValueError as exc:st.error(str(exc))
    return pending_question


def student(rt):
    from ui.design import page_header
    page_header('AI解题与辅导','上传题目或打开老师批改过的作业，选择提示、分步讲解或完整解答。','我的学习 / 数学答疑')
    sid=student_id(rt)
    upload,existing=st.tabs(['开始提问','我的作业'])
    with upload:
        pending_question=student_composer(rt,sid)
    own=[s for s in rt.w['submissions'] if s['student_id']==sid]
    batches={batch['id']:batch['name'] for batch in rt.w['batches']}
    def source_name(row):
        return batches.get(row.get('batch_id'),'自主学习' if row['source']=='self_study' else '教师作业')
    with existing:
        if not own:
            st.info('暂无作业。收到老师分享的链接后，按学号查看。')
        else:
            st.caption('选择下方题目可查看原作答、批改结果并继续辅导。')
            st.dataframe([{'作业':source_name(s),'题号':s['question_no'],'题目':s['question'][:100],
                           '判断':LABEL[p.effective(rt.w,s)['verdict']]} for s in reversed(own)],
                         hide_index=True,width='stretch')
    if not own:
        empty('从一道题开始','自主拍题或输入题目后，可以直接请求讲解。');return
    ids=[s['id'] for s in own];focus=st.session_state.pop('v12_sub_pending',None)
    if focus in ids:st.session_state['v12_sub']=focus
    elif st.session_state.get('v12_sub') not in ids:st.session_state['v12_sub']=ids[0]
    labels={s['id']:source_name(s)+' · '+(s['question_no'] or s['topic'])+' · '+s['question'][:60] for s in own}
    selected=st.selectbox('当前学习题目',ids,key='v12_sub',format_func=labels.get)
    sub=next(s for s in own if s['id']==selected)
    source_batch=next((b for b in rt.w['batches'] if b['id']==sub.get('batch_id')),None)
    if source_batch:st.caption('来自教师作业：'+source_batch['name']+' · 第 '+(sub.get('question_no') or '未编号')+' 题，无需重新上传。')
    left,right=st.columns([1,1.3],gap='large')
    with left,surface():
        st.subheader('题目与原有解答')
        source_panel(rt,e.student_material(rt.w,sub),show_student=False)
        result=e.latest_success(sub)
        if result:
            st.caption('作答分析')
            message(result['analysis']['method_summary'])
            first=result['analysis']['first_error_step']
            if first:st.write('首个可确认错误：第 '+str(first)+' 步')
        review=c.latest_review(rt.w,sub['id'])
        state=p.effective(rt.w,sub)
        if review and (not sub.get('reference_revision') or state['confirmed'] or review['analysis_id']==state['source_id']):
            st.info('教师意见：'+review['label']+'；'+review['note'])
        if st.button('分析我的错误',disabled=not rt.ready() or not bool(sub['steps'] or sub['answer'])):
            q=p.quick_check(sub,rt.call)
            if q['status']=='completed' and q['verdict']!='correct':p.deep_analyze(sub,rt.call)
            p.sync_notebook(rt.w,sub['id']);rt.persist();st.rerun()
    with right,surface():
        from core import agent as tutoring_agent
        current=tutoring_agent.latest_run(rt.w,sub['id'],sid)
        default='深度辅导' if current and current['status']!='cancelled' else '直接答疑'
        assistance=st.segmented_control('辅导方式',['直接答疑','深度辅导'],default=default,required=True,key='tutoring_mode_'+sub['id'])
        if assistance=='深度辅导':
            st.subheader('深度辅导')
            from ui.agent import render as render_agent
            render_agent(rt,sub)
        else:
            if current and current['status']!='cancelled':
                tutoring_agent.cancel(rt.w,sub['id'],sid);rt.persist()
            st.subheader('这次，怎样帮助你？')
            modes={'hint':'先给提示','steps':'分步引导','full':'查看完整解答'}
            mode=st.segmented_control('解题方式',list(modes),default=next(iter(modes)),format_func=lambda k:modes[k],required=True,key='solve_mode')
            if st.button('获取所选讲解',type='primary',disabled=not rt.ready()):
                with st.spinner('结合原题和当前解答分析…'):
                    p.solve_question(sub,mode,rt.call)
                if p.effective(rt.w,sub)['verdict']=='incorrect':p.sync_notebook(rt.w,sub['id'])
                rt.persist();st.rerun()
            solution=p.latest(sub,'solutions')
            if sub.get('solutions') and sub['solutions'][-1]['status']=='failed':st.error(sub['solutions'][-1]['error'])
            if solution:
                st.caption('本次讲解：'+modes[solution['mode']])
                st.write('已知条件：'+'；'.join(solution['known_conditions']))
                st.write('求解目标：'+solution['goal']);message(solution['method']);show_correction(solution['correction'])
            elif p.correction_for(sub):
                show_correction(p.correction_for(sub))
            st.divider();st.subheader('继续追问这道题')
            session=next((t for t in rt.w['study_sessions'] if t['submission_id']==sub['id']),None)
            for turn in (session or {}).get('turns',[]):
                if turn['reply']:
                    with st.chat_message('user'):st.write(turn['reply'])
                with st.chat_message('assistant'):
                    message(turn['message'])
                    if turn['next_suggestion']:st.caption(turn['next_suggestion'])
            level=st.select_slider('提示等级',options=[1,2,3,4],format_func=lambda n:['方向提示','思路提示','关键步骤','完整讲解'][n-1])
            a,b=st.columns(2)
            ask=a.button('请 AI 主动问我一个关键问题',disabled=not rt.ready())
            hint=b.button('按当前等级给提示',disabled=not rt.ready())
            pending=st.session_state.get(pending_question,{})
            draft=pending.get('text','') if sub['id'] in pending.get('ids',[]) else ''
            reply_key='v12_reply_'+sub['id']
            if st.session_state.pop(reply_key+'_clear',False):
                st.session_state.pop(reply_key,None)
            if draft and not st.session_state.get(reply_key):
                st.session_state[reply_key]=draft
            reply=st.text_area('继续追问 / 回答 AI',max_chars=2000,key=reply_key,placeholder='例如：第二步为什么可以这样变形？')
            send=st.button('发送问题或回答',disabled=not rt.ready())
            if ask or hint or send:
                try:
                    p.study_turn(rt.w,sub,'ask_student' if ask else 'hint' if hint else 'reply',reply if send else '',rt.call,level)
                    if send:
                        if draft:st.session_state.pop(pending_question,None)
                        st.session_state[reply_key+'_clear']=True
                    rt.persist();st.rerun()
                except (ValueError,RuntimeError) as exc:rt.persist();st.error(str(exc))
    st.divider()
    no_work=not bool(sub['steps'] or sub['answer'])
    cause=st.selectbox('收录时的主要错因',[p.UNKNOWN]+p.CATEGORIES,index=(p.CATEGORIES.index('暂无解题思路')+1) if no_work else 0)
    confirm=st.checkbox('我确认本题的错因分类',value=False)
    if st.button('加入 / 更新我的错题本',type='primary'):
        try:
            item=p.sync_notebook(rt.w,sub['id'],manual=True,chosen_category=cause)
            p.edit_entry(rt.w,item['id'],cause,[],item['notes'],confirmed=confirm)
            rt.persist();st.success('已收录，同一学生同一题不会重复添加。')
        except ValueError as exc:st.error(str(exc))
    st.button('查看我的错题本',on_click=go,args=('学生学习空间','我的错题本'))

def book_filters(rt,sid,prefix='book'):
    rows=p.notebook_rows(rt.w,sid)
    search,filters=st.columns([4,1])
    query=search.text_input('搜索错题',placeholder='搜索题目中的文字或公式…',key=prefix+'_search',label_visibility='collapsed')
    with filters.popover('筛选',width='stretch'):
        cause=st.selectbox('错因筛选',['全部',p.UNKNOWN]+p.CATEGORIES,key=prefix+'_cause')
        dates=st.date_input('记录时间范围',value=(date.fromisoformat(min((n['created_at'][:10] for n in rows),default=date.today().isoformat())),date.today()),key=prefix+'_dates')
    if len(dates)!=2:return []
    return p.notebook_rows(rt.w,sid,query,cause=None if cause=='全部' else cause,start=dates[0],end=dates[1])

def open_book_entry(entry_id):
    st.session_state['v12_book_pending']=entry_id
    st.session_state['book_type']='全部错题'
    st.session_state['book_cause']='全部'
    st.session_state['book_search']=''
    go('学生学习空间','我的错题本')

def notebook_cause_text(item, sub=None):
    if item['primary_category']!=p.UNKNOWN:
        return '主要错因：'+item['primary_category']
    diagnostic=p.current_deep(sub) if sub else None
    return '暂无法确定错因' if diagnostic and diagnostic.get('correction') else '错因尚未分析'


def notebook_detail(rt,sid,item):
    sub=next((s for s in rt.w['submissions'] if s['id']==item['submission_id'] and s['student_id']==sid
              and p.item_key(s)==item.get('question_id',p.question_key(item['question']))),None)
    with surface():
        st.markdown('<div class="section-heading"><h3>错题详情</h3>'+badge(v.kind(item))+'</div>',unsafe_allow_html=True)
        source_batch=next((b for b in rt.w['batches'] if b['id']==(sub or {}).get('batch_id')),None)
        if source_batch:st.caption('来自教师作业：'+source_batch['name']+' · 第 '+(sub.get('question_no') or '未编号')+' 题')
        original,solution,knowledge=st.tabs(['原题与错误','正确解法','相关公式与方法'])
        with original:
            message(item.get('edited_question',item['question']))
            if sub:
                with st.expander('原始作答与原图',expanded=True):source_panel(rt,e.student_material(rt.w,sub),show_student=False)
            else:
                for line in item['original_steps']:message(line)
                st.write('原始答案：'+item['original_answer'])
            state=p.effective(rt.w,sub) if sub else None
            first=item.get('first_error_step')
            if state and state['source_id'] and state['verdict'] in ('correct','incorrect'):
                st.markdown('**批改结果：** '+LABEL[state['verdict']])
                st.write('批改依据：'+state['basis'])
            a=p.current_deep(sub) if sub else None
            if first:
                st.markdown(f'**错误位置：** 第 {first} 步')
                step=next((s for s in a['analysis']['steps'] if s['number']==first),None) if a else None
                if step:message(step['observation'])
            elif state and state['verdict']=='incorrect':
                st.caption('尚未定位到具体出错步骤。')
            classification=notebook_cause_text(item,sub)
            badge_state=('本人已确认' if item['category_confirmed'] else '待确认') if item['primary_category']!=p.UNKNOWN else ''
            st.markdown(badge(classification)+(badge(badge_state) if badge_state else ''),unsafe_allow_html=True)
            if item['notes']:
                st.write('我的备注：'+item['notes'])
            elif item['primary_category']!=p.UNKNOWN or classification=='暂无法确定错因':
                st.write(item['ai_category_basis'])
            if not item.get('active_error',True):st.info('这道题已移出错因统计，历史记录仍可查看。')
            related=[s for s in rt.w['submissions'] if s['student_id']==sid and s['id'] in item.get('source_ids',[])
                     and s['id']!=item['submission_id'] and p.item_key(s)==item.get('question_id',p.question_key(item['question']))]
            if related:
                with st.expander('本人本题的其他作答'):
                    for row in related:source_panel(rt,e.student_material(rt.w,row),show_student=False)
        with solution:
            message(item['correct_answer'])
            for i,step in enumerate(item['reference_steps'],1):
                message('**'+str(i)+'.** '+step['text']);st.caption('依据：'+step['reason'])
            for warning in item['uncertainties']:st.warning(warning)
            st.caption({'partial':'部分步骤已有数学核验。','checked':'已完成可用的数学核验。'}.get(item['reference_tool']['status'],'请结合原题条件核对参考解。')+' AI结论仍可能出错。')
        with knowledge:
            if not item['supplements']:st.write('暂无补充公式或方法。')
            for supplement in item['supplements']:
                message(supplement['content'])
                st.caption('使用条件：'+supplement['conditions'])
                st.write('与本题的关系：'+supplement['connection'])
            if st.button('按当前错因补充讲解',disabled=not rt.ready() or sub is None):
                p.solve_question(sub,'full',rt.call,force=True,cause=item['primary_category'])
                p.sync_notebook(rt.w,sub['id'],manual=True,chosen_category=item['primary_category'])
                rt.persist();st.rerun()
        st.divider()
        st.markdown('**还有哪一步不明白？**')
        if sub and st.button('继续向 AI 追问',type='primary',key='continue_book_'+item['id']):
            st.session_state['v12_sub_pending']=sub['id'];go('学生学习空间','AI 解题与辅导');st.rerun()
        st.caption('收录于 '+item['created_at'][:10]+' · '+('自主学习' if item['origin']=='self_study' else '作业批改'))
    with st.expander('修改错因与题目记录'):
        with st.form('book_edit_'+item['id']):
            question_type=st.selectbox('题型',['未分类']+v.TYPES,index=(['未分类']+v.TYPES).index(v.kind(item)))
            options=[p.UNKNOWN]+p.CATEGORIES
            primary=st.selectbox('主要错因',options,index=options.index(item['primary_category']),
                                 format_func=lambda value:'暂不分类' if value==p.UNKNOWN else value)
            secondary=st.multiselect('次要错因（最多2项）',p.CATEGORIES,default=item['secondary_categories'],max_selections=2)
            question=st.text_area('个人题目修订（不改写教师原题）',value=item.get('edited_question',item['question']),max_chars=4000)
            notes=st.text_area('我的备注',value=item['notes'],max_chars=2000)
            confirmed=st.checkbox('确认这次错因分类',value=item['category_confirmed'])
            if st.form_submit_button('保存错因与个人修订',type='primary'):
                try:
                    p.edit_entry(rt.w,item['id'],primary,secondary,notes,confirmed,question)
                    v.edit_type(rt.w,item['id'],question_type);rt.persist();st.rerun()
                except ValueError as exc:st.error(str(exc))
    with st.expander('历史记录与其他操作'):
        st.dataframe([{'时间':event['created_at'][:19],'操作':event['action'],'此前分类':event.get('previous',{}).get('primary_category','')}
            for event in rt.w['book_events'] if event['entry_id']==item['id']],hide_index=True,width='stretch')
        if st.checkbox('确认移入已删除记录',key='delete_confirm_'+item['id']) and st.button('删除这道错题'):
            p.delete_entry(rt.w,item['id']);rt.persist();st.rerun()

def notebook(rt):
    from ui.design import page_header
    sid=student_id(rt)
    page_header('我的错题本','查看原作答、批改依据和参考解法。','我的学习 / 错题整理',str(len(p.notebook_rows(rt.w,sid)))+' 道错题')
    selected_type=st.segmented_control('题型分类',['全部错题']+v.TYPES,default='全部错题',selection_mode='single',required=True,key='book_type')
    rows=book_filters(rt,sid)
    sources={sub['id']:sub for sub in rt.w['submissions'] if sub['student_id']==sid}
    if selected_type!='全部错题':rows=[n for n in rows if v.kind(n)==selected_type]
    unknown=sum(v.kind(n)=='未分类' for n in p.notebook_rows(rt.w,sid))
    if unknown:st.caption(str(unknown)+' 道旧错题尚未标注题型，在“全部错题”可查看并补充。')
    focus=st.session_state.pop('v12_book_pending',None)
    if focus in [n['id'] for n in rows]:st.session_state['v12_book_entry']=focus
    left,right=st.columns([1,1.55],gap='large')
    with left:
        st.subheader('错题列表')
        with st.container(height=660,border=False):
            if not rows:empty('当前没有匹配的错题','试试其他题型，或从 AI 解题与辅导收录一道题。')
            for n in rows:
                with surface():
                    st.markdown(badge(v.kind(n))+'<span class="note-date">'+safe(n['created_at'][:10])+'</span>',unsafe_allow_html=True)
                    message(n.get('edited_question',n['question']))
                    st.caption(notebook_cause_text(n,sources.get(n['submission_id'])))
                    st.button('查看解析',key='open_note_'+n['id'],width='stretch',
                        on_click=lambda nid=n['id']:st.session_state.update(v12_book_entry=nid))
    with right:
        item=next((n for n in rows if n['id']==st.session_state.get('v12_book_entry')),None)
        if item:notebook_detail(rt,sid,item)
        else:empty('选择一道错题','点击左侧“查看解析”，这里会展示题目、错误与正确解法。')
    with st.expander('已删除记录 / 恢复'):
        for n in [n for n in rt.w['notebook'] if n['student_id']==sid and n['deleted']]:
            if st.button('恢复：'+n['question'][:50],key='restore_'+n['id']):
                p.delete_entry(rt.w,n['id'],False);rt.persist();st.rerun()
    st.download_button('导出我的错题记录',dumps(rows),'mindtrace_notebook.json','application/json')
    st.caption('仅导出我的当前筛选结果，不包含原图。')

def causes(rt):
    from datetime import timedelta
    from ui.design import page_header,metric
    from ui.pie import cause_pie
    sid=student_id(rt)
    head,scope=st.columns([3,1],gap='large')
    with head:
        page_header('错因分析','查看已归类错题。点击一个错因可打开对应题目。','我的学习 / 学习洞察')
    with scope:
        period=st.selectbox('统计范围',['全部记录','最近7天','最近30天'],key='cause_period')
    start=None if period=='全部记录' else date.today()-timedelta(days=6 if period=='最近7天' else 29)
    rows=p.notebook_rows(rt.w,sid,start=start)
    groups,unknown=v.cause_distribution(rows)
    slices,total,unknown=v.cause_slices(rows)
    a,b,c1=st.columns([1.4,1,1],gap='large')
    with a:metric('已归类错题',total,'每道错题只记录一个主要错因',accent=True,icon_name='book')
    with b:metric('主要错因',len(groups),'点击饼图或类别，查看对应题目',icon_name='chart')
    with c1:metric('暂无法归类',unknown,'未归类的错题不计入图表',icon_name='review')
    if not groups:
        empty('还没有可统计的错因','从一道错题开始。保存并归类后，就能看到自己的错因分布。')
        return
    selected=st.session_state.get('cause_selected')
    if selected not in groups:selected=slices[0]['label'];st.session_state['cause_selected']=selected
    left,right=st.columns([1.45,1],gap='large')
    with left,surface(key='cause_chart'):
        st.subheader('主要错因分布')
        st.caption('点击图中的错因，查看对应错题。')
        event=cause_pie(slices,total,selected,key='cause_pie_'+sid)
        if isinstance(event,dict) and event.get('event_id')!=st.session_state.get('last_cause_event'):
            st.session_state['last_cause_event']=event.get('event_id')
            if event.get('label') in groups:
                st.session_state['cause_selected']=event['label'];st.rerun()
    with right,surface(key='cause_legend'):
        st.subheader('错因与题目')
        for item in slices:
            label=item['label'];g=groups[label]
            st.markdown('<div class="cause-legend-label"><i style="background:'+item['color']+'"></i><span>'+safe(label)+'</span><b>'+str(item['count'])+' 题</b><em>'+item['percent_label']+'%</em></div>',unsafe_allow_html=True)
            st.button('查看'+label,key='cause_category_'+label,width='stretch',
                type='primary' if selected==label else 'secondary',
                on_click=lambda label=label:st.session_state.update(cause_selected=label))
            st.caption('本人确认 '+str(g['confirmed'])+' · 待确认 '+str(g['suggested']))
    selected=st.session_state['cause_selected']
    linked=[n for n in rows if n['id'] in groups[selected]['ids']]
    st.markdown('<div class="section-heading"><h3>'+safe(selected)+'</h3><span class="section-count">'+str(len(linked))+' 道错题</span></div>',unsafe_allow_html=True)
    cards=st.columns(2,gap='large')
    for index,n in enumerate(linked):
        with cards[index%2],surface():
            st.markdown(badge(v.kind(n))+'<span class="note-date">'+safe(n['created_at'][:10])+'</span>',unsafe_allow_html=True)
            message(n.get('edited_question',n['question']))
            st.caption('主要错因：'+n['primary_category']+' · '+('本人确认' if n['category_confirmed'] else '待确认'))
            st.button('查看原题与解析',key='cause_note_'+n['id'],on_click=open_book_entry,args=(n['id'],))



def landing(rt):
    st.markdown(
        '<div class="landing-intro landing-classic"><span class="eyebrow">'+BRAND_TITLE+'</span>'
        '<h1>学然后知不足，<br>教然后知困。</h1><cite>《礼记·学记》</cite>'
        '<p>循理是高中数学批改与辅导平台。教师批量批改、查看班级易错题；学生根据原作答追问和练习。</p></div>',
        unsafe_allow_html=True,
    )
    st.session_state.setdefault('home_preselection','teacher')
    with st.container(key='home_role_grid'):
        a,b=st.columns(2,gap='medium')
    entries=[(a,'teacher','教师工作空间','批改作业，发现共性问题','批量上传，按题查看错误人数，打开原卷复核。','进入教师工作台','教师工作空间','作业批改'),
             (b,'student','学生学习空间','读懂批改，巩固错题','查看老师批改的作业，或拍题获取分步讲解。','进入学生学习中心','学生学习空间','AI解题与辅导')]
    for col,value,kicker,heading,description,enter,role,destination in entries:
        selected=st.session_state['home_preselection']==value
        with col,surface(key='home_'+value):
            st.button(kicker+'\n\n**'+heading+'**\n\n'+description,key='home_select_'+value,
                type='primary' if selected else 'secondary',width='stretch',
                on_click=lambda choice=value:st.session_state.update(home_preselection=choice))
            st.button(enter,key='home_enter_'+value,type='primary' if selected else 'secondary',width='stretch',on_click=go,args=(role,destination))

def sync_notebook_sources(rt,sid=None):
    # Rerendering unchanged pages must not traverse and resync every notebook entry.
    # Keep a read-time repair path for legacy records and cross-browser updates.
    records=[sub for sub in rt.w['submissions'] if sid is None or sub['student_id']==sid]
    ids={sub['id'] for sub in records}
    sources=[(sub['id'],sub.get('question_type'),sub.get('question_no'),sub.get('parent_question_no'),sub.get('subquestion_no'),sub.get('image_ref'),
              [(key,(sub.get(key) or [{}])[-1].get('id'),(sub.get(key) or [{}])[-1].get('status'))
               for key in ('quick_checks','analyses','solutions')]) for sub in records]
    token=p.digest([rt.w['id'],sid,sources,[r['id'] for r in rt.w['reviews'] if r['submission_id'] in ids]])
    if st.session_state.get('v12_notebook_sources')==token:return
    before=len(rt.w['book_events'])
    for sub in records:
        if p.latest(sub,'quick_checks') or e.latest_success(sub):p.sync_notebook(rt.w,sub['id'])
    if len(rt.w['book_events'])!=before:rt.persist()
    st.session_state['v12_notebook_sources']=token


def render(page,root,shared,key=None):
    rt=Runtime(root,shared,key);p.ensure(rt.w);st.session_state['_surface_index']=0
    if page in ('AI解题与辅导','我的错题本','错因分析'):
        student_identity_panel(rt)
        sync_notebook_sources(rt,student_id(rt))
    else:
        sync_notebook_sources(rt)
    if any(s['source']=='heatmap_acceptance_fixture' for s in rt.w['submissions']):
        st.caption('验收构造数据：批改与确认由测试脚本生成，仅用于核对界面和统计，不代表真实课堂或模型评测。')
    if any(s['source'] in ('constructed_examples','live_constructed_fixture','v12_constructed_live') for s in rt.w['submissions']):
        st.caption('当前包含构造匿名材料；真实接口返回不代表真实学生学习效果。')
    {'产品首页':landing,'作业批改':teacher,'班级错误分析':insights,'历史记录':history,
     'AI解题与辅导':student,'我的错题本':notebook,'错因分析':causes}[page](rt)
    st.markdown('<div class="footer"><span>'+BRAND_TITLE+'</span></div>',unsafe_allow_html=True)

