"""Two teacher intake routes that converge on the existing grading workflow."""
import pandas as pd
import streamlit as st

from core import uploads as u
from core.product import digest
from ui.experience import surface


def teacher_upload(rt, mode, save):
    pdf=mode=='pdf'
    root='assignment_upload_'+mode
    version=st.session_state.get(root+'_version',0)
    prefix=f'{root}_{version}'
    maximum=u.MAX_TEACHER_FILES if pdf else u.MAX_PHOTOS
    size=st.get_option('server.maxUploadSize')
    limit=size*1024*1024
    with surface(key=root):
        st.subheader('批量上传学生 PDF' if pdf else '上传单名学生的作业图片')
        st.caption('每名学生一份 PDF，一次导入全班作业。' if pdf else '适合手机拍摄，可上传同一名学生的多张作业照片。')
        st.caption(f'每次最多 {maximum} 份 · 单文件最多 {size} MB · 合计最多 512 MB'+
                   (' · 每份 PDF 最多 24 页' if pdf else ' · PNG / JPG / WEBP'))
        files=st.file_uploader('选择或拖入 PDF' if pdf else '选择或拖入同一学生的照片',
                               type=['pdf'] if pdf else ['png','jpg','jpeg','webp'],
                               accept_multiple_files=True,key=prefix+'_files')
        if files:
            total=sum(f.size for f in files)
            display_size=f'{total/1024**2:.1f} MB' if total>=1024**2 else f'{total/1024:.1f} KB'
            st.caption(f'已上传 {len(files)} / {maximum} 份 · {display_size}。可用上传列表的 × 删除或替换单个文件。')
        signature=tuple(f.file_id for f in files)
        queue=st.session_state.setdefault(prefix,{'signature':None,'documents':{},'states':{},'order':[]})
        if queue['signature']!=signature:
            try:documents=u.upload_documents(files,mode,limit)
            except ValueError as exc:
                st.error(str(exc))
                return
            queue['signature']=signature
            queue['documents']=documents
            previous=queue['order']
            retained=[k for k in previous if k in documents]
            queue['order']=retained+[k for k in documents if k not in retained]
            active={d['file_id'] for d in documents.values()}
            queue['states']={key:value for key,value in queue['states'].items() if key in active}
            if not pdf:
                first=next((i for i,(a,b) in enumerate(zip(previous,queue['order'])) if a!=b),len(retained))
                for key in queue['order'][first:]:
                    queue['states'].pop(documents[key]['file_id'],None)
        if queue['documents']:
            review_upload(rt,queue,prefix,mode,limit,save,root,version)


def review_upload(rt,queue,prefix,mode,limit,save,root,version):
    pdf=mode=='pdf'
    documents,order,states=(queue[key] for key in ('documents','order','states'))
    duplicates=u.duplicate_files(documents)
    statuses={}
    display=[]
    complete=0
    recognized=0
    for index,key in enumerate(order,1):
        doc=documents[key]
        state=states.get(doc['file_id'],{})
        error=doc['error'] or ('文件内容重复，请移除副本。' if key in duplicates else '')
        statuses[key]=error
        done=len(state.get('drafts',{}))
        pages=len(state.get('pages',[]))
        recognized+=done
        complete+=bool(pages and done==pages and not error)
        display.append({'序号':index,'文件':doc['name'],
                        '识别进度':f'{done} / {pages} 页' if pages else '待解析',
                        '状态':error or state.get('error') or ('已识别' if pages and done==pages else '待识别')})
    st.dataframe(display,hide_index=True,width='stretch',height=min(350,38+35*len(display)))
    st.progress(complete/len(order),text=f'{complete} / {len(order)} 份文件已识别 · 共 {recognized} 页')
    names={key:f'{index}. {documents[key]["name"]}' for index,key in enumerate(order,1)}
    selected=st.selectbox('选择要核对的文件' if pdf else '选择要预览或调整的照片',
                          order,format_func=names.get,key=prefix+'_selected')
    doc=documents[selected]
    state=states.get(doc['file_id'],{})
    if not pdf:
        pos=order.index(selected)
        up,down=st.columns(2)
        direction=-1 if up.button('上移一页',disabled=pos==0,key=prefix+'_up') else (
                  1 if down.button('下移一页',disabled=pos==len(order)-1,key=prefix+'_down') else 0)
        if direction:
            order[pos],order[pos+direction]=order[pos+direction],order[pos]
            # Cross-page references depend on page order and must be reviewed again.
            for key in order[min(pos,pos+direction):]:states.pop(documents[key]['file_id'],None)
            st.rerun()
    if not doc['error'] and (state.get('pages') or not pdf):
        pages=state.get('pages') or [doc['data']]
        number=st.selectbox('原始页码',range(1,len(pages)+1),key=prefix+'_page_'+selected) if pdf else 1
        with st.expander('查看原始页面',expanded=not pdf):
            st.image(pages[number-1],width=450)
            if number-1 in state.get('drafts',{}):
                draft=state['drafts'][number-1]
                st.caption(f"本页识别到 {len(draft['records'])} 条题目、{len(draft['answers'])} 条独立作答。")
                if draft.get('reused_question_page'):st.caption('本页复用了本批中完全相同的试题页。')
                if draft.get('split_page'):st.caption('本页分区识别，请对照原图核对分界处。')
    if duplicates:st.warning('发现重复文件，请从上传列表移除副本。')
    st.caption('全部页面识别完成后，会按题号匹配本份作业的题目和作答。整份作业确实未答的题计错。')
    if state.get('error'):
        st.warning(doc['name']+' · '+state['error'])
    consent=st.checkbox('文件已匿名化，同意发送页面图像进行识别。',key=prefix+'_consent')
    ready=consent and rt.ready()
    active=[key for key in order if not statuses[key]]
    unfinished=any(not states.get(documents[k]['file_id'],{}).get('pages') or
                   len(states[documents[k]['file_id']]['drafts'])<len(states[documents[k]['file_id']]['pages'])
                   for k in active)
    start,retry=st.columns(2)
    started=recognized or any(s.get('splits') for s in states.values())
    run=start.button('识别下一批页面' if started else '开始识别作业',key=prefix+'_run',
                     type='primary',disabled=not (ready and unfinished))
    single=retry.button('重试当前文件',key=prefix+'_retry',
                        disabled=not (ready and not statuses[selected] and state.get('error')))
    if run or single:
        progress=st.empty()
        keys=([selected] if pdf else order[:order.index(selected)+1]) if single else active
        if mode=='photos' and len(active)!=len(order):
            st.warning('请先处理照片冲突，再按页序识别。')
            return
        def update(name,page,total,region):
            finished=sum(len(s['drafts']) for s in states.values())
            stage=region if region=='复用相同题面' else f'正在识别{region}' if region else '等待识别服务返回本页结果'
            progress.info(f'{name} · 第 {page} / {total} 页 · {stage}。本批已完成 {finished} 页。')
        def call_page(*args,**kwargs):
            with st.spinner('正在等待当前识别请求',show_time=True):
                return rt.call(*args,**kwargs)
        queue['notice']=u.process_pages(documents,keys,states,call_page,mode=mode,limit_bytes=limit,progress=update)
        rt.persist()
        st.rerun()
    if queue.get('notice'):st.info(queue['notice'])
    if not rt.ready():st.info('AI 服务尚未启用。文件可先上传，配置服务后再识别。')
    if complete!=len(order):return
    try:
        materials,rows=u.assemble_materials(documents,order,states,mode=mode)
    except ValueError as exc:
        st.warning(str(exc))
        if st.button('重新识别所选页',key=prefix+'_retry_link',disabled=not ready):
            for index in range(number-1,len(state['pages'])):
                state['drafts'].pop(index,None)
                state.get('splits',{}).pop(index,None)
                state.setdefault('fresh_pages',set()).add(index)
            st.rerun()
        return
    st.subheader('校对识别结果')
    st.caption('可修正题干、作答和题型，或取消保留误识别的题目。')
    columns={'keep':'保留','source_file':'作业文件','source_pages':'来源页','question_no':'题号','question_type':'题型',
             'parent_question_no':'大题号','subquestion_no':'小问号','question':'题目','steps':'解题步骤','answer':'最终答案'}
    editable=list(columns)
    review_key=prefix+'_review_'+digest([rows,[(m['student_id'],m['identity_status'],
                            [page['original_image'] for page in m['pages']]) for m in materials]])[:16]
    filenames={m['student_id']:m['pages'][0]['filename'] for m in materials}
    frame=pd.DataFrame(rows).assign(keep=True,source_file=lambda data:data['student_id'].map(filenames))
    editor=st.data_editor(frame[editable],hide_index=True,width='stretch',
                          disabled=['source_file','source_pages'],column_config=columns,
                          key=review_key)
    confirmed=st.checkbox('我已核对原始页面和识别结果。',key=review_key+'_confirmed')
    if st.button('确认校对并保存材料',key=prefix+'_save',type='primary',disabled=not confirmed):
        try:
            fields=[k for k in editable if k not in ('keep','source_file','source_pages')]
            edited=[dict(raw,**{k:change[k] for k in fields})
                    for raw,change in zip(rows,editor.fillna('').to_dict('records')) if change['keep']]
            if {row['student_id'] for row in edited}!={material['student_id'] for material in materials}:
                raise ValueError('每名学生至少保留一道可批改题目；如整份文件无法使用，请从上传列表移除。')
            sources={doc['file_id']:doc['data'] for doc in documents.values()}
            evidence={draft['image_ref']:state['pages'][index] for state in states.values()
                      for index,draft in state['drafts'].items()}
            save(edited,materials,sources,evidence)
            st.session_state[root+'_version']=version+1
            del st.session_state[prefix]
            st.rerun()
        except (OSError,ValueError) as exc:st.error(str(exc))
