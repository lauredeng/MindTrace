"""Student corrections, spaced review and teacher feedback with shared evidence."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from core import classroom as c, learning_records as learning, review_scheduler as review, product as p, answer_keys
from ui.workbench import message
from ui.design import page_header,metric
from ui.experience import surface,badge,empty
from html import escape

LABEL={'correct':'正确','incorrect':'仍需订正','uncertain':'待进一步核对'}


def command(rt,path,payload,local):
    from core import backend_client
    if rt.access and backend_client.enabled():
        rt.persist(strict=True)
        result=backend_client.request('POST',path,code=rt.access['code'],data=payload)
        rt.prepare_workspace()
        return result
    if rt.access and path=='/corrections':
        from core.learning_service import submit
        rt.persist(strict=True)
        result=submit(rt.access['code'],payload)
        rt.prepare_workspace()
        return result
    result=local()
    if path=='/corrections':learning.compare_correction(rt.w,result['id'])
    rt.persist(strict=True)
    return result


def attempts_for(rt,sub):
    return [a for a in rt.w.get('correction_attempts',[]) if a['submission_id']==sub['id'] and a['student_id']==sub['student_id']]


def correction_form(rt,sub,*,prefix='correction',origin='correction'):
    learning.ensure(rt.w)
    key=prefix+'_'+sub['id']
    st.markdown('#### '+('重新独立作答' if origin=='review' else '提交原题订正'))
    st.caption('原作答与本次作答分别保存。教师可查看订正过程并留下反馈。')
    prior=attempts_for(rt,sub)
    with st.form(key,clear_on_submit=True):
        process,material=st.columns([1.3,1],gap='large')
        with process:
            steps=st.text_area('本次解题过程',height=260,max_chars=8000,placeholder='逐行填写推导过程，保留关键条件和理由。')
        with material:
            answer=st.text_area('本次最终答案',max_chars=2000,height=90)
            files=st.file_uploader('手写订正附件（图片或 PDF，可选）',type=['png','jpg','jpeg','pdf'],accept_multiple_files=True)
        helped=st.checkbox('本次使用了提示或他人帮助')
        revealed=st.checkbox('本次作答前查看过参考答案或完整讲解')
        submitted=st.form_submit_button('提交作答',type='primary')
    if submitted:
        try:
            solution=p.latest(sub,'solutions')
            seen=bool(prefix=='tutor_correction' and solution and solution.get('mode')=='full')
            refs=[]
            if files:
                from core.uploads import expand_files
                pages,errors=expand_files(files,allow_pdf=True,max_files=3,max_pages=12)
                if errors:raise ValueError('附件未能完整读取，请检查文件大小和页数。')
                refs=[rt.keep_image(data) for _,data in pages]
            args=dict(command_id=c.uid(),independent=not helped and not revealed and not seen,
                hint_used=helped,answer_revealed=revealed or seen,origin=origin,attachment_refs=refs,
                parent_id=prior[-1]['id'] if prior else None)
            command(rt,'/corrections',dict(submission_id=sub['id'],expected_fingerprint=sub['fingerprint'],
                expected_reference_revision=sub.get('reference_revision'),expected_grading_revision=sub.get('grading_revision'),
                steps=[line.strip() for line in steps.splitlines() if line.strip()],answer=answer,**args),
                lambda:learning.submit_correction(rt.w,sub['id'],sub['student_id'],steps,answer,**args))
            st.rerun()
        except (ValueError,RuntimeError) as exc:st.error(str(exc))


def show_attempt(rt,attempt,*,teacher=False,prefix='attempt'):
    assessment=learning.latest_assessment(rt.w,attempt)
    with surface():
        st.markdown(badge('独立作答' if attempt['independent'] else '借助提示或参考')+' '+
                    badge(LABEL[assessment['verdict']] if assessment else '待教师复核','purple'),unsafe_allow_html=True)
        for number,step in enumerate(attempt['steps'],1):message(f'**{number:02d}**　{step}')
        message('**答案：** '+attempt['answer'])
        for ref in attempt.get('attachment_refs',[]):
            image=rt.image(ref)
            if image:st.image(image,width='stretch')
            else:st.warning('订正附件暂时无法读取，请保留原文件并联系教师。')
        timestamp=datetime.fromisoformat(attempt['created_at']).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%m月%d日 %H:%M')
        st.caption(timestamp+' · '+('复习作答' if attempt['origin']=='review' else '原题订正'))
        if assessment:
            st.info(('教师反馈：' if assessment['method']=='teacher' else '核验反馈：')+assessment['note'])
        if teacher:
            key=prefix+'_'+attempt['id']
            if st.button('按已确认参考答案核验',key=key+'_local'):
                try:
                    result=command(rt,'/corrections/'+attempt['id']+'/compare',None,lambda:learning.compare_correction(rt.w,attempt['id']))
                    if result['comparable']:st.rerun()
                    st.info('本题不能仅凭答案自动核验，请结合下方过程复核。')
                except (ValueError,RuntimeError) as exc:st.error(str(exc))
            with st.form(key+'_review'):
                verdict=st.segmented_control('订正结论',list(LABEL),format_func=LABEL.get,required=True,default='uncertain')
                note=st.text_area('反馈与依据',max_chars=2000,placeholder='说明本次作答已解决的问题，或仍需修改的具体步骤。')
                save=st.form_submit_button('保存订正反馈',type='primary')
            if save:
                try:
                    command_id=c.uid()
                    command(rt,'/corrections/'+attempt['id']+'/review',dict(verdict=verdict,note=note,command_id=command_id),
                        lambda:learning.assess_correction(rt.w,attempt['id'],verdict,note,command_id=command_id))
                    st.rerun()
                except (ValueError,RuntimeError) as exc:st.error(str(exc))


def teacher_corrections(rt,sub,*,prefix='feedback'):
    learning.ensure(rt.w)
    attempts=attempts_for(rt,sub)
    st.subheader('原题订正与反馈')
    if not attempts:
        st.caption('学生提交订正后，原答与新作答会分别保留在这里。');return
    for attempt in reversed(attempts[-5:]):show_attempt(rt,attempt,teacher=True,prefix=prefix)


def student_workspace(rt,*,view='review'):
    from ui.product import student_id
    sid=student_id(rt);learning.ensure(rt.w)
    own=[s for s in rt.w['submissions'] if s['student_id']==sid]
    if view=='profile':return profile_page(rt,sid)
    page_header('订正与复习','保留每一次作答，在反馈与独立重做中巩固理解。','我的学习 / 学习进程')
    attempts=[a for a in rt.w['correction_attempts'] if a['student_id']==sid]
    due=review.due(rt.w,sid)
    pending=sum(learning.latest_assessment(rt.w,a) is None for a in attempts)
    with st.container(key='learning_metrics'):
        a,b,d=st.columns(3)
        with a:metric('待复习',len(due),'按有效复习记录安排',accent=True,icon_name='book')
        with b:metric('待教师反馈',pending,'已提交的原题订正',icon_name='review')
        with d:metric('作答记录',len(attempts),'原答与订正分别保存',icon_name='check')
    correction_tab,review_tab,history_tab=st.tabs(['原题订正','复习计划','作答记录'])
    with correction_tab:
        if not own:empty('还没有可订正的题目','查看老师批改的作业，或上传一道自己的题目。')
        else:
            by_id={s['id']:s for s in own}
            selected=st.selectbox('选择题目',list(by_id),format_func=lambda key:('第 '+by_id[key]['question_no']+' 题' if by_id[key].get('question_no') else '自主题目')+' · '+by_id[key]['topic'],key='learning_hub_sub')
            sub=by_id[selected];message(sub['question'])
            correction_form(rt,sub,prefix='hub')
    with review_tab:
        st.caption('完成一次作答并取得可靠核验后，再记录难度。查看解析或聊天不会自动推进复习计划。')
        units=[u for u in rt.w['review_units'] if u['student_id']==sid]
        if own:
            by_id={s['id']:s for s in own}
            with st.popover('加入复习计划'):
                target=st.selectbox('复习题目',list(by_id),format_func=lambda key:by_id[key]['question'][:70])
                objective=st.selectbox('复习目标',['独立重做','关键条件回忆','关键步骤重建'])
                if st.button('加入计划',type='primary'):
                    command(rt,'/learning/units',dict(submission_id=target,objective=objective),lambda:review.add_unit(rt.w,target,sid,objective=objective));st.rerun()
        if not units:empty('从一道值得重做的题开始','加入计划后，可在这里查看复习时间、提交新作答并记录难度。')
        for unit in units:
            source=learning.owned_submission(rt.w,unit['submission_id'],sid)
            current=review.state(rt.w,unit)
            with surface():
                st.markdown(badge(unit['objective'])+' '+badge('需重新确认' if current['stale'] else '已到复习时间' if current['card'].due<=review.utc() else '按计划复习','purple'),unsafe_allow_html=True)
                message(source['question'])
                if current['stale']:st.info('题目或参考答案已更新，旧计划不再推进。请为新版重新加入复习计划。');continue
                due_text=current['card'].due.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%m月%d日 %H:%M')
                st.caption('下次复习：'+due_text+' · 有效复习 '+str(current['valid_reviews'])+' 次')
                with st.popover('提交复习作答',width='stretch'):
                    correction_form(rt,source,prefix='due_'+unit['id'],origin='review')
                candidates=[a for a in attempts_for(rt,source) if a['origin']=='review' and learning.latest_assessment(rt.w,a)
                            and not any(ev['unit_id']==unit['id'] and ev['attempt_id']==a['id'] for ev in rt.w['review_events'])]
                if candidates:
                    with st.form('rate_'+unit['id']):
                        attempt_id=st.selectbox('已核验作答',[a['id'] for a in candidates],format_func=lambda key:next(a['created_at'][:16]+' · '+LABEL[learning.latest_assessment(rt.w,a)['verdict']] for a in candidates if a['id']==key))
                        rating=st.segmented_control('完成难度',[1,2,3,4],format_func=lambda n:['未能完成','较吃力','顺利完成','轻松完成'][n-1],required=True,default=3)
                        submit=st.form_submit_button('更新复习计划')
                    if submit:
                        try:
                            command_id=c.uid()
                            command(rt,'/learning/reviews',dict(unit_id=unit['id'],attempt_id=attempt_id,rating=rating,command_id=command_id),
                                lambda:review.record_review(rt.w,unit['id'],sid,attempt_id,rating,command_id=command_id))
                            st.rerun()
                        except (ValueError,RuntimeError) as exc:st.warning(str(exc))
    with history_tab:
        if not attempts:st.info('尚无订正或复习作答。')
        for attempt in reversed(attempts[-20:]):show_attempt(rt,attempt)


def profile_page(rt,sid):
    projection=learning.profile(rt.w,sid)
    page_header('学习画像','从具体作答中观察变化，每一项记录均可回到原题。','我的学习 / 学习证据')
    points=projection['points']
    if not points:empty('学习证据仍在积累','完成作答、订正或复习后，这里会呈现可追溯的记录。');return
    fields=[('independent_success','独立完成','#4564e6'),('assisted_success','借助帮助完成','#aebaf7'),
            ('original_correct','原答正确','#72b8a1'),('original_incorrect','原答错误','#e3b77c')]
    maximum=max(1,max(sum(row[field] for field,_,_ in fields) for row in points))
    legend=''.join('<span><i style="background:'+color+'"></i>'+label+'</span>' for _,label,color in fields)
    bars=[]
    for point in points:
        segments=''.join('<i title="'+label+' '+str(point[field])+' 次" style="width:'+str(100*point[field]/maximum)+'%;background:'+color+'"></i>' for field,label,color in fields if point[field])
        bars.append('<div class="learning-bar-row"><b>'+escape(point['label'])+'</b><div class="learning-bar-track">'+segments+'</div><span>'+str(sum(point[field] for field,_,_ in fields))+' 条</span></div>')
    st.markdown('<div class="learning-chart" role="img" aria-label="各知识领域的作答证据条数"><div class="learning-legend">'+legend+'</div>'+''.join(bars)+'</div>',unsafe_allow_html=True)
    st.caption('图表统计作答次数，同一题多次订正分别记录；不换算为能力分数。')
    for point in points:
        with surface():
            st.markdown('#### '+point['label'])
            st.caption('独立完成 '+str(point['independent_success'])+' 次 · 借助帮助完成 '+str(point['assisted_success'])+' 次 · 原答待复核 '+str(point['unconfirmed'])+' 次')
            sources={s['id']:s for s in rt.w['submissions'] if s['student_id']==sid}
            table=[{'题目':('第 '+sources[e['submission_id']]['question_no']+' 题' if sources[e['submission_id']].get('question_no') else '自主题目'),
                           '来源':{'original':'原作答','review':'复习','transfer':'变式验证','correction':'订正'}[e['kind']],
                           '结果':('AI初判 · ' if e['kind']=='original' and not e.get('confirmed') else '')+LABEL[e['verdict']],
                           '独立完成':('是' if e.get('independent') else '否') if e['kind']!='original' else '—'} for e in point['evidence']]
            selected=st.dataframe(table,hide_index=True,width='stretch',on_select='rerun',selection_mode='single-row',key='profile_evidence_'+p.digest(point['label'])[:12])
            indices=selected.selection.rows
            if indices:
                source=point['evidence'][indices[0]];message(source.get('question',sources[source['submission_id']]['question']))
                from ui.experience import go
                st.button('打开原题与辅导',key='open_profile_'+p.digest(point['label'])[:12],on_click=go,
                          args=('学生学习空间','AI解题与辅导',source['submission_id']))
            else:st.caption('选中一条记录可查看原题，并继续学习。')
    st.caption(projection['limitation'])
