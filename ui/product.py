"""V1.2 streamlined teacher and student product surfaces."""
from datetime import date
from collections import Counter
import io
import json
import pandas as pd
import streamlit as st
from core import product as p, education as e, classroom as c, presentation as v
from ui.workbench import Runtime,image_input,manual_form,source_panel,message,dumps
from ui.experience import title,card,surface,empty,badge,topic_chips,go,safe

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
    st.markdown('<div class="learning-pipeline"><span class="active">01 上传与归属</span><span>02 识别校对</span><span>03 批改与深析</span><span>04 班级统计</span></div>',unsafe_allow_html=True)
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


def teacher(rt):
    from ui.design import page_header
    toolbar=st.columns([1,1,4])
    with toolbar[0].popover('切换作业',width='stretch'):
        batch=batch_picker(rt)
    if batch:
        if toolbar[1].button('上传新作业',width='stretch'):
            st.session_state['show_assignment_upload']=not st.session_state.get('show_assignment_upload',False)
    else:
        page_header('把作业带进来，让问题清晰起来。','导入全班 PDF 或单名学生的照片，核对后开始批改。','教师工作台 / 作业批改')
    if not batch or st.session_state.get('show_assignment_upload',False):
        with surface(key='upload_assignment'):
            upload_assignment(rt)
    if not batch:return
    execution=p.batch_execution(rt.w,batch['id'])
    def execute_batch():
        progress=st.progress(0,text='准备批改，已成功结果将复用…')
        def update(stage,i,n):
            progress.progress((0 if stage=='quick' else .5)+.5*i/n,text=('快速批改' if stage=='quick' else '错题与疑点深析')+f' {i}/{n}')
            rt.persist()
        try:
            p.run_batch(rt.w,batch['id'],rt.call,update,_prepare=rt.prepare_workspace,_persist=rt.persist)
        except RuntimeError:
            st.warning('这份作业可能正在另一窗口处理，请稍后刷新查看；本窗口未继续重复批改。')
            return
        st.rerun()
    if execution['status'] in ('failed','partial','paused') or (batch.get('status')=='running' and execution['remaining']):
        action='继续未完成的批改' if execution['status']=='paused' or batch.get('status')=='running' else '重试未完成的批改'
        if st.button(action,type='primary',disabled=not rt.ready(),key='retry_batch_'+batch['id']):execute_batch()
        st.caption('保留并复用已成功的批改和深析，只请求未完成的步骤；不会自动反复重试。')
    with st.popover('批改操作'):
        if st.button('开始批改并分析错题',type='primary',disabled=not rt.ready() or not execution['remaining']):execute_batch()
        st.caption('复用成功结果，重试未完成的批改。')
    from ui.results import results
    results(rt,batch,selected_case,view='grading')


def question_table(rows):
    st.dataframe([{'题号':g['label'],'题目':g['question'][:100],'已判':g['valid'],
        '正确':g['correct'],'错误':g['errors'],'留白（已计错）':g['not_submitted'],
        '未判定':g['pending'],'无法识别':g['unreadable']} for g in rows],hide_index=True,width='stretch')

def transcription_editor(rt,sub,state,key):
    if not sub.get('batch_id') or not sub.get('image_ref'):
        return
    first=state['first_error_step']
    if first and 1<=first<=len(sub['steps']):
        st.warning(f'请先对照原图核对第 {first} 行，再确认该处是否为学生错误。')
        st.text(sub['steps'][first-1])
    with st.expander('校正转写并单题重判'):
        if not rt.image(sub['image_ref']):
            st.info('原图暂不可用，无法对照校正。')
            return
        st.caption('按原图校正作答文字。保存后旧判定退出当前统计，原图及历史记录保留。')
        form_key=key+'_transcription_'+sub['id']+'_'+sub['fingerprint']
        with st.form(form_key):
            steps=st.text_area('作答步骤 · 每行一步',value='\n'.join(sub['steps']),max_chars=8000)
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
                                            prepare=rt.prepare_workspace,persist=rt.persist)
                st.rerun()
            except (OSError,RuntimeError,ValueError) as exc:
                st.warning(str(exc))


def selected_case(rt,subs,key='v12_case'):
    if not subs:return
    filters=['全部','优先看异常','错误','正确']
    filter_value=st.segmented_control('作答筛选',filters,default=filters[0],required=True,key=key+'_filter')
    selected=[s for s in subs if filter_value=='全部' or
        (filter_value=='优先看异常' and p.effective(rt.w,s)['verdict']=='uncertain') or
        (filter_value=='错误' and p.effective(rt.w,s)['verdict']=='incorrect') or
        (filter_value=='正确' and p.effective(rt.w,s)['verdict']=='correct')]
    if not selected:
        st.info('当前筛选没有作答。');return
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
    a,b=st.columns([1,1.15],gap='large')
    with a,surface():
        st.subheader('原始题目与作答');source_panel(rt,sub,show_student=sub['student_id'] not in filenames)
        upload_provenance(rt,sub,key)
        transcription_editor(rt,sub,state,key)
    with b,surface():
        st.subheader('批改依据')
        st.markdown(badge(LABEL[state['verdict']])+badge('教师判定' if state['confirmed'] else '卷面留白' if p.is_blank(sub) else '自动批改'),unsafe_allow_html=True)
        st.write(state['basis'])
        failed=False
        for key_name in ('quick_checks','analyses'):
            if sub.get(key_name) and sub[key_name][-1]['status']=='failed':
                failed=True
                st.error('最近一次未完成：'+sub[key_name][-1]['error'])
        if failed and sub.get('batch_id') and st.button('重试本题批改',key=key+'_retry_'+sub['id'],disabled=not rt.ready()):
            try:
                with st.spinner('正在重试这一题的未完成步骤…'):
                    p.run_batch(rt.w,sub['batch_id'],rt.call,lambda *_:rt.persist(),
                                _prepare=rt.prepare_workspace,_persist=rt.persist,submission_id=sub['id'])
                st.rerun()
            except (OSError,RuntimeError,ValueError) as exc:
                st.warning(str(exc))
        quick=p.latest(sub,'quick_checks')
        if quick:
            st.text('引用的作答转写：'+quick['evidence_quote'])
        if not state['confirmed'] and p.latest(sub,'quick_checks') and state['verdict']!='uncertain' and v.record_state(rt.w,sub) not in ('unreadable','not_submitted'):
            if st.button('确认这份批改',key=key+'_confirm_'+sub['id']):
                try:v.confirm_short(rt.w,sub['id']);rt.persist();st.rerun()
                except ValueError as exc:st.error(str(exc))
        if not p.is_blank(sub):
            with st.expander('教师改判'):
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

    with st.expander('学生学习反馈'):
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
            with st.expander('查看本次辅导动作与证据'):
                for trace in latest_run['trace']:
                    if trace.get('policy')=='allowed':
                        st.write(tutoring_agent.ACTIONS[trace['action']]+'：'+trace['rationale'])
                        st.caption('证据引用：'+'、'.join(trace['evidence_ids']))
                    elif trace.get('observation'):st.caption('未执行动作：'+trace['observation'].get('reason','不满足条件'))
                verified=next((r['practice'] for r in reversed(runs) if r.get('practice',{}).get('attempts')),None)
                if verified:st.write('新题验证：'+e.learning_state(verified['attempts']))
        st.caption('学生的自报错因与追问属于学习反馈，不会自动改写教师确认的正误或证明已经掌握。')

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
    if not material:return
    pages=material['pages']
    st.caption('本题来源页 · '+'、'.join(map(str,sub['source_pages'])))
    with st.expander('查看整份作业的原始文件与页码'):
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
    title('HISTORY / 历史记录','保存每一次批改的来源与修订。','查看批次、原始证据与教师复核，按需导出；无需生成教学计划。')
    batch=batch_picker(rt)
    if not batch:
        st.info('还没有新版本批次。旧记录在高级选项的兼容工作区中保留。');return
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
    if getattr(rt,'assigned_student',None):
        st.session_state['studio_current_student']=rt.assigned_student
        return rt.assigned_student
    from uuid import uuid4
    pending=st.session_state.pop('v12_student_pending',None)
    current=pending or st.session_state.get('studio_current_student')
    if not current:
        ids=list(dict.fromkeys(s['student_id'] for s in rt.w['submissions']))
        current=rt.w.get('demo_student_id') or (ids[0] if ids else 'STU-'+uuid4().hex[:10])
    st.session_state['studio_current_student']=current
    return current


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

def student(rt):
    from ui.design import page_header
    page_header('AI解题与辅导','拍一道题，选择需要的解释。提示、分步或完整解答，都由你决定。','我的学习 / 数学答疑')
    sid=student_id(rt)
    if not sid:st.info('先填写匿名编号，再保存题目。');return
    upload,existing=st.tabs(['拍题 / 上传解答','教师批改与已有题目'])
    with upload,st.expander('上传题目或补充文字',expanded=not any(s['student_id']==sid for s in rt.w['submissions'])):
        photo,text=st.tabs(['图片识别与校对','文字输入'])
        with photo:
            st.caption('没有解答也能保存题目。不确定的条件请对照图片确认。')
            saved=image_input(rt,'v12_student',True,allow_unanswered=True,student_id=sid)
            if saved:
                st.session_state['v12_student_pending']=saved[0]['student_id'];st.session_state['v12_sub_pending']=saved[0]['id'];st.rerun()
        with text:
            row=manual_form('v12_student_text',student_id=sid,hide_student=True)
            if row:
                try:
                    sub=rt.add(row,'self_study',allow_unanswered=True)
                    st.session_state['v12_sub_pending']=sub['id'];st.session_state['v12_student_pending']=sub['student_id'];st.rerun()
                except ValueError as exc:st.error(str(exc))
    own=[s for s in rt.w['submissions'] if s['student_id']==sid]
    with existing:
        st.caption('老师批改过的原题与作答会直接显示在这里，无需重新输入。')
        st.dataframe([{'题号':s['question_no'],'题目':s['question'][:100],'来源':'自主学习' if s['source']=='self_study' else '教师作业',
                       '判断':LABEL[p.effective(rt.w,s)['verdict']]} for s in own],hide_index=True,width='stretch')
    if not own:
        empty('先带来一道你想弄懂的题','上传题目或解答，或者使用教师已经导入的匿名编号。无需创建学习任务。');return
    ids=[s['id'] for s in own];focus=st.session_state.pop('v12_sub_pending',None)
    if focus in ids:st.session_state['v12_sub']=focus
    elif st.session_state.get('v12_sub') not in ids:st.session_state['v12_sub']=ids[0]
    selected=st.selectbox('当前学习题目',ids,key='v12_sub',format_func=lambda k:next((s['question_no'] or s['topic'])+' · '+s['question'][:60] for s in own if s['id']==k))
    sub=next(s for s in own if s['id']==selected)
    source_batch=next((b for b in rt.w['batches'] if b['id']==sub.get('batch_id')),None)
    if source_batch:st.caption('来自教师作业：'+source_batch['name']+' · 第 '+(sub.get('question_no') or '未编号')+' 题，无需重新上传。')
    left,right=st.columns([1,1.3],gap='large')
    with left,surface():
        st.subheader('题目与原有解答')
        source_panel(rt,e.student_material(rt.w,sub),show_student=False)
        result=e.latest_success(sub)
        if result:
            st.caption('已观察到的数学问题')
            message(result['analysis']['method_summary'])
            first=result['analysis']['first_error_step']
            if first:st.write('首个可确认错误：第 '+str(first)+' 步')
        review=c.latest_review(rt.w,sub['id'])
        if review:st.info('教师意见：'+review['label']+'；'+review['note'])
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
            level=st.select_slider('提示等级',options=[1,2,3,4],format_func=lambda n:['方向提示','思路提示','关键步骤','完整讲解'][n-1])
            a,b=st.columns(2)
            ask=a.button('请 AI 主动问我一个关键问题',disabled=not rt.ready())
            hint=b.button('按当前等级给提示',disabled=not rt.ready())
            reply=st.text_area('继续追问 / 回答 AI',max_chars=2000,key='v12_reply_'+sub['id'],placeholder='例如：第二步为什么可以这样变形？还有其他解法吗？')
            send=st.button('发送问题或回答',disabled=not rt.ready())
            if ask or hint or send:
                try:
                    p.study_turn(rt.w,sub,'ask_student' if ask else 'hint' if hint else 'reply',reply if send else '',rt.call,level)
                    rt.persist();st.rerun()
                except (ValueError,RuntimeError) as exc:rt.persist();st.error(str(exc))
            session=next((t for t in rt.w['study_sessions'] if t['submission_id']==sub['id']),None)
            for turn in (session or {}).get('turns',[]):
                with st.container(border=True):
                    if turn['reply']:st.write('我的问题 / 回答：'+turn['reply'])
                    message(turn['message']);st.caption('这次在解决：'+turn['purpose'])
                    if turn['next_suggestion']:st.caption('可选下一步：'+turn['next_suggestion'])
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
            first=item.get('first_error_step')
            st.markdown('**错误位置：** '+('第 '+str(first)+' 步' if first else '暂未确定'))
            a=p.current_deep(sub) if sub else None
            if a and first:
                step=next((s for s in a['analysis']['steps'] if s['number']==first),None)
                if step:message(step['observation'])
            st.markdown(badge(item['primary_category'])+badge('本人已确认' if item['category_confirmed'] else 'AI建议 · 待确认'),unsafe_allow_html=True)
            st.write(item['notes'] or item['ai_category_basis'])
            st.caption('AI最初分类：'+item.get('initial_ai_category',item['ai_category'])+'。认知原因只是本题解释，不代表长期能力。')
            if not item.get('active_error',True):st.info('这条记录已退出当前错因统计，历史仍可查看。')
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
            if not item['supplements']:st.write('本题暂不需要额外知识讲义。')
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
        st.caption('把这道题和原始作答带入辅导，继续问原因、步骤或其他解法。')
        if sub and st.button('继续向 AI 追问',type='primary',key='continue_book_'+item['id']):
            st.session_state['v12_sub_pending']=sub['id'];go('学生学习空间','AI 解题与辅导');st.rerun()
        st.caption('收录于 '+item['created_at'][:10]+' · '+('自主学习' if item['origin']=='self_study' else '作业批改'))
    with st.expander('修改错因与题目记录'):
        with st.form('book_edit_'+item['id']):
            question_type=st.selectbox('题型',['未分类']+v.TYPES,index=(['未分类']+v.TYPES).index(v.kind(item)))
            primary=st.selectbox('主要错因',[p.UNKNOWN]+p.CATEGORIES,index=([p.UNKNOWN]+p.CATEGORIES).index(item['primary_category']))
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
    page_header('我的错题本','原题、错误和正确解法，放在一起慢慢弄懂。','我的学习 / 错题整理',str(len(p.notebook_rows(rt.w,sid)))+' 道错题')
    selected_type=st.segmented_control('题型分类',['全部错题']+v.TYPES,default='全部错题',selection_mode='single',required=True,key='book_type')
    rows=book_filters(rt,sid)
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
                    st.caption('主要错因：'+n['primary_category'])
                    st.button('查看解析',key='open_note_'+n['id'],width='stretch',
                        on_click=lambda nid=n['id']:st.session_state.update(v12_book_entry=nid))
    with right:
        item=next((n for n in rows if n['id']==st.session_state.get('v12_book_entry')),None)
        if item:notebook_detail(rt,sid,item)
        else:empty('选择一道错题，开始阅读','点击左侧“查看解析”，这里会展示题目、错误与正确解法。')
    with st.expander('已删除记录 / 恢复'):
        for n in [n for n in rt.w['notebook'] if n['student_id']==sid and n['deleted']]:
            if st.button('恢复：'+n['question'][:50],key='restore_'+n['id']):
                p.delete_entry(rt.w,n['id'],False);rt.persist();st.rerun()
    st.download_button('导出我的错题记录',dumps(rows),'mindtrace_notebook.json','application/json')
    st.caption('仅导出我的当前筛选结果，不包含原图。')

def causes(rt):
    from datetime import timedelta
    from ui.design import page_header,metric,note
    from ui.pie import cause_pie
    sid=student_id(rt)
    head,scope=st.columns([3,1],gap='large')
    with head:
        page_header('错因分析','从具体错题出发，看清反复出现的问题。','我的学习 / 学习洞察')
    with scope:
        period=st.selectbox('统计范围',['全部记录','最近7天','最近30天'],key='cause_period')
    start=None if period=='全部记录' else date.today()-timedelta(days=6 if period=='最近7天' else 29)
    rows=p.notebook_rows(rt.w,sid,start=start)
    groups,unknown=v.cause_distribution(rows)
    slices,total,unknown=v.cause_slices(rows)
    top=next(iter(slices),None)
    a,b,c1=st.columns([1.4,1,1],gap='large')
    with a:metric('已归类错题',total,'每道错题只记录一个主要错因',accent=True,icon_name='book')
    with b:metric('主要错因',len(groups),'点击饼图或类别，查看对应题目',icon_name='chart')
    with c1:metric('暂无法归类',unknown,'证据不足的记录不进入饼图',icon_name='review')
    if not groups:
        empty('还没有可统计的错因','从一道错题开始。保存并归类后，就能看到自己的错因分布。')
        return
    selected=st.session_state.get('cause_selected')
    if selected not in groups:selected=slices[0]['label'];st.session_state['cause_selected']=selected
    left,right=st.columns([1.45,1],gap='large')
    with left,surface(key='cause_chart'):
        st.subheader('主要错因分布')
        st.caption('扇区面积代表已归类错题的占比。点击扇区，下方显示该类错题。')
        event=cause_pie(slices,total,selected,key='cause_pie_'+sid)
        if isinstance(event,dict) and event.get('event_id')!=st.session_state.get('last_cause_event'):
            st.session_state['last_cause_event']=event.get('event_id')
            if event.get('label') in groups:
                st.session_state['cause_selected']=event['label'];st.rerun()
        st.caption(f'当前范围共 {total} 道已归类错题；不含证据不足、已删除及已修正为正确的记录。百分比四舍五入显示。')
    with right,surface(key='cause_legend'):
        st.subheader('错因与题目')
        for item in slices:
            label=item['label'];g=groups[label]
            st.markdown('<div class="cause-legend-label"><i style="background:'+item['color']+'"></i><span>'+safe(label)+'</span><b>'+str(item['count'])+' 题</b><em>'+item['percent_label']+'%</em></div>',unsafe_allow_html=True)
            st.button('查看'+label,key='cause_category_'+label,width='stretch',
                type='primary' if selected==label else 'secondary',
                on_click=lambda label=label:st.session_state.update(cause_selected=label))
            st.caption('本人确认 '+str(g['confirmed'])+' · 待确认 '+str(g['suggested']))
        if top:
            note('目前最常见：'+top['label'],str(top['count'])+' 道相关错题。一次错误并不等于长期能力判断，先回到原题核对。')
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
    st.markdown('<div class="landing-intro"><span class="eyebrow">MINDTRACE · 知错 AI</span><h1>看清每一道错题，<br>弄懂每一步数学。</h1><p>面向高中数学的智能作业批改、错因诊断与个性化学习平台。</p></div>',unsafe_allow_html=True)
    st.session_state.setdefault('home_preselection','teacher')
    a,b=st.columns(2,gap='large')
    entries=[(a,'teacher','教师工作空间','批改一批作业，看见班级问题','快速批改，自动深析错误和疑点。按题查看错误人数，追溯原始作答，按需复核与导出。','进入教师工作台','教师工作空间','作业批改'),
             (b,'student','学生学习空间','从一道疑问，到真正理解','拍题或读取老师的批改，选择提示、分步或完整解答；继续追问，再将错误整理进智能错题本。','进入学生学习中心','学生学习空间','AI解题与辅导')]
    for col,value,kicker,heading,description,enter,role,destination in entries:
        selected=st.session_state['home_preselection']==value
        with col,surface(key='home_'+value):
            st.button(kicker+'\n\n**'+heading+'**\n\n'+description,key='home_select_'+value,
                type='primary' if selected else 'secondary',width='stretch',
                on_click=lambda choice=value:st.session_state.update(home_preselection=choice))
            st.button(enter,key='home_enter_'+value,type='primary' if selected else 'secondary',width='stretch',on_click=go,args=(role,destination))
    st.markdown('<div class="trust-strip"><span>◎ 原始证据可追溯</span><span>◎ 不强制追问或训练</span><span>◎ 错因可以确认与修正</span></div>',unsafe_allow_html=True)
    st.caption('当前是单机演示。角色切换不是身份认证；模型判断可能出错，重要结论请复核。')

def sync_notebook_sources(rt):
    # Rerendering unchanged pages must not traverse and resync every notebook entry.
    # Keep a read-time repair path for legacy records and cross-browser updates.
    sources=[(sub['id'],sub.get('question_type'),sub.get('question_no'),sub.get('parent_question_no'),sub.get('subquestion_no'),sub.get('image_ref'),
              [(key,(sub.get(key) or [{}])[-1].get('id'),(sub.get(key) or [{}])[-1].get('status'))
               for key in ('quick_checks','analyses','solutions')]) for sub in rt.w['submissions']]
    token=p.digest([rt.w['id'],sources,[r['id'] for r in rt.w['reviews']]])
    if st.session_state.get('v12_notebook_sources')==token:return
    before=len(rt.w['book_events'])
    for sub in list(rt.w['submissions']):
        if p.latest(sub,'quick_checks') or e.latest_success(sub):p.sync_notebook(rt.w,sub['id'])
    if len(rt.w['book_events'])!=before:rt.persist()
    st.session_state['v12_notebook_sources']=token


def render(page,root,shared,key=None):
    rt=Runtime(root,shared,key);p.ensure(rt.w);st.session_state['_surface_index']=0
    sync_notebook_sources(rt)
    if any(s['source']=='heatmap_acceptance_fixture' for s in rt.w['submissions']):
        st.caption('验收构造数据：批改与确认由测试脚本生成，仅用于核对界面和统计，不代表真实课堂或模型评测。')
    if any(s['source'] in ('constructed_examples','live_constructed_fixture','v12_constructed_live') for s in rt.w['submissions']):
        st.caption('当前包含构造匿名材料；真实接口返回不代表真实学生学习效果。')
    {'产品首页':landing,'作业批改':teacher,'班级错误分析':insights,'历史记录':history,
     'AI解题与辅导':student,'我的错题本':notebook,'错因分析':causes}[page](rt)
    st.markdown('<div class="footer"><span>MindTrace · 知错 AI</span><span>数学结论请结合原始证据核对</span></div>',unsafe_allow_html=True)

