"""Shared classroom UI helpers. Models run only on explicit actions."""
from copy import deepcopy
import hashlib
import io
import json
import pandas as pd
import streamlit as st
from core import ai, classroom as store, education as edu, collaboration as collab
from core.usage import for_session
from core.limits import UsageLimitError
from core.uploads import expand_files

PAGES = ['班级学情工作台', '学生学习中心', '学习证据画像', '调用与任务记录']
VERDICT = {'correct': '合理', 'incorrect': '存在错误', 'uncertain': '证据不足'}

def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2)

def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()

def message(value):
    st.markdown(value.replace('\\[', '$$').replace('\\]', '$$').replace('\\(', '$').replace('\\)', '$'))

def heading(kicker, title, caption):
    st.markdown('<div class="eyebrow">' + kicker + '</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(caption)

def status(sub, workspace=None):
    if not sub['analyses']:
        return '等待分析'
    a = sub['analyses'][-1]
    if a['status'] == 'failed':
        return '分析未完成'
    reviewed=store.latest_review(workspace,sub['id']) if workspace else None
    if reviewed and reviewed['analysis_id']==a['id']:
        return {'confirm':'教师已确认','modify':'教师已修改确认','reject':'教师已驳回','uncertain':'教师标记无法判断'}[reviewed['decision']]
    return 'AI / 工具冲突' if a.get('conflicts') else 'AI 已分析 · 待复核'

class Runtime:
    def __init__(self, root, shared, api_key):
        self.root, self.shared, self.key = root, shared or st.session_state.get('collab_guest',False), api_key
        self.access=st.session_state.get('collab_access')
        if self.access:
            from core import collaboration as collab
            self.access=collab.resolve(self.access['code'])
            self.shared=False
        self.assigned_student=(self.access or {}).get('student_id')
        if 'studio_workspace' not in st.session_state:
            try:
                st.session_state.studio_workspace = store.new_workspace() if self.shared else (collab.load(self.access['code']) if self.access else store.load())
            except (OSError, ValueError):
                st.error('教学工作区读取失败，原文件未改动。')
                st.stop()
        self.w = st.session_state.studio_workspace
        self.before=deepcopy(st.session_state.get('collab_snapshot',self.w))
        self.session = st.session_state.ai_usage_id
        st.session_state.setdefault('studio_images', {})

    def ready(self):
        return bool(self.key) if self.key is not None else ai.ai_ready()

    def call(self, system, user, **kwargs):
        return ai.completion([{'role':'system','content':system},{'role':'user','content':user}],
                             api_key=self.key, session_id=self.session, **kwargs)

    def prepare_workspace(self):
        # Call inside an execution lease, before deciding which paid steps remain.
        if self.access:
            collab.adopt(self.w,collab.load(self.access['code']))
            self.before=deepcopy(self.w);st.session_state['collab_snapshot']=deepcopy(self.w)
        elif not self.shared:
            latest=store.load()
            if latest['id']==self.w['id'] and latest['storage_version']>self.w['storage_version']:
                collab.adopt(self.w,latest)
        return self.w

    def prepare_agent(self):
        return self.prepare_workspace()

    def persist(self):
        known = {e['id'] for e in self.w['usage']}
        self.w['usage'].extend(e for e in for_session(self.session) if e['id'] not in known)
        if not self.shared:
            try:
                if self.access:
                    from core import collaboration as collab
                    version=collab.save(self.access['code'],self.before,self.w)
                    self.w['storage_version']=version
                    self.before=deepcopy(self.w);st.session_state['collab_snapshot']=deepcopy(self.w)
                else:store.save(self.w)
            except (OSError, ValueError) as exc:
                if self.access:
                    st.error('课堂保存未完成，未覆盖其他人的记录。请先复制当前内容，刷新课堂后重试。');st.stop()
                else:st.warning('页面数据仍在，但本机保存失败，请下载备份。')

    def image(self, ref):
        if not ref:
            return None
        return st.session_state.studio_images.get(ref) or (None if self.shared else store.read_image(ref,collab.image_directory(self.access['code']) if self.access else None))

    def keep_image(self, data):
        ref = hashlib.sha256(data).hexdigest()
        st.session_state.studio_images[ref] = data
        if not self.shared:
            try:
                store.attach_image(data,collab.image_directory(self.access['code']) if self.access else None)
            except OSError:
                st.warning('原图仍可在当前会话对照，但磁盘保存失败，请自行保留匿名原图。')
        return ref

    def upload_evidence(self, ref, *, original=False, data=None):
        if self.assigned_student:
            raise ValueError('原始上传文件仅对教师开放。')
        directory=collab.image_directory(self.access['code']) if self.access else store.DATA_DIR/'classroom_images'
        cache=st.session_state.studio_images
        if original:
            directory=directory/'originals'
            if self.shared:cache=st.session_state.setdefault('studio_original_uploads',{})
        if data is None:
            return cache.get(ref) if self.shared else store.read_image(ref,directory)
        if hashlib.sha256(data).hexdigest()!=ref:
            raise ValueError('原始文件校验失败，请重新上传。')
        if self.shared:cache[ref]=data
        else:store.attach_image(data,directory)

    def add(self, row, source='manual', image_ref=None, transcription='', allow_unanswered=False):
        sub = edu.normalize_submission(row, source, image_ref, transcription, allow_unanswered=allow_unanswered)
        same = next((s for s in self.w['submissions'] if s['fingerprint']==sub['fingerprint'] and s.get('image_ref')==image_ref), None)
        if same:
            return same
        store.commit(self.w, 'submission-'+sub['fingerprint']+str(image_ref), lambda w:w['submissions'].append(sub))
        self.persist()
        return self.w['submissions'][-1]

def manual_form(prefix, student_id='', hide_student=False):
    with st.form(prefix+'_material'):
        if hide_student:
            b,c=st.columns([1,3]);sid=student_id
        else:
            a,b,c=st.columns([1,1,2])
            sid=a.text_input('匿名学习编号', value=student_id, max_chars=80, key=prefix+'_sid')
        qno=b.text_input('题目编号', max_chars=80, key=prefix+'_qno')
        topic=c.selectbox('知识模块',edu.TOPICS,key=prefix+'_topic')
        question_type=st.selectbox('题型',['未分类']+edu.QUESTION_TYPES,key=prefix+'_question_type')
        question=st.text_area('完整题目与条件',max_chars=4000,height=110,key=prefix+'_question',
                              placeholder='高中各数学模块均可提交，不以数学工具支持范围设门槛。')
        steps=st.text_area('学生解题过程 · 每行一步',max_chars=8000,height=140,key=prefix+'_steps')
        answer=st.text_area('学生最终答案（可空）',max_chars=2000,key=prefix+'_answer')
        with st.expander('可选局部数学核验'):
            kind=st.selectbox('核验类型',['general','derivative','equation'],
                format_func=lambda k:{'general':'自动尝试，工具不适用仍交给 AI','derivative':'多项式求导','equation':'多项式方程'}[k],key=prefix+'_kind')
            expr=st.text_input('求导原函数（仅求导工具需要）',max_chars=160,key=prefix+'_expr')
        submit=st.form_submit_button('使用这道题' if hide_student else '保存作业材料',type='primary')
    return dict(student_id=sid,question_no=qno,topic=topic,question=question,steps=steps,answer=answer,task_type=kind,tool_expression=expr,question_type=question_type) if submit else None

def image_input(rt,prefix,self_study=False,allow_unanswered=False,student_id=None,on_save=None,known_questions=None,class_batch=False,*,files=None):
    attached=files is not None
    if not attached:
        formats=['png','jpg','jpeg','webp']+(['pdf'] if class_batch else [])
        upload_label='上传作业图片或 PDF' if class_batch else '上传题目照片' if self_study else '上传作业图片'
        files=st.file_uploader(upload_label,type=formats,accept_multiple_files=True,key=prefix+'_photos')
    if class_batch:
        st.caption('单张图片 ≤ 8 MB，单份 PDF ≤ 24 MB、24 页，整批 ≤ 128 MB。试题和作答应在同一页；分开的试卷与答题卡需先配对。')
    with (st.popover('识别选项') if attached else st.expander('识别选项')):
        force_ocr=st.checkbox('重新识别，不复用此前转写（将再次调用 AI）',key=prefix+'_force_ocr')
    signature=tuple((f.file_id,f.name,f.size) for f in files)
    queue_key=prefix+'_upload_queue'
    queue=st.session_state.get(queue_key)
    if not queue or queue['signature']!=signature:
        try:
            if attached:
                pages,errors=expand_files(files,allow_pdf=True,max_files=5,max_pages=12)
            else:
                pages,errors=expand_files(files,allow_pdf=class_batch)
        except ValueError as exc:
            pages,errors=[],[('本次上传',str(exc))]
        unique={}
        for name,data in pages:
            unique.setdefault(hashlib.sha256(data).hexdigest(),(name,data))
        drafts={key:queue['drafts'][key] for key in unique if queue and key in queue['drafts']}
        queue={'signature':signature,'pages':unique,'errors':errors,'drafts':drafts,'failed':{}}
        st.session_state[queue_key]=queue
    pages=queue['pages']
    for name,error in queue['errors']:
        st.error(name+'：'+error)
    if attached and not pages:return []
    if pages:
        preview=st.selectbox('预览附件页面' if attached else '预览原始图片',list(pages),format_func=lambda digest:pages[digest][0],key=prefix+'_preview')
        st.image(pages[preview][1],width=480)
    consent_label='我已移除个人信息，同意发送附件页面供 AI 识别。' if attached else '图片已经匿名化，同意发送至模型进行真实识别。'
    consent_key=prefix+'_consent'+('_'+digest(signature)[:12] if attached else '')
    consent=st.checkbox(consent_label,key=consent_key)
    if st.button('识别附件' if attached else '识别图片中的题目与步骤',type='primary',disabled=not(pages and consent and rt.ready()),key=prefix+'_ocr'):
        if force_ocr:
            queue['drafts'].clear()
        queue['failed'].clear()
        progress=st.progress(len(queue['drafts'])/len(pages))
        for image_hash,(name,data) in pages.items():
            if image_hash in queue['drafts']:
                continue
            try:
                with st.spinner('正在转写 '+name+'…'):
                    catalog=dict.fromkeys(row['question'] for prior in queue['drafts'].values() for row in prior['records'])
                    shared=[{'id':hashlib.sha256(question.encode()).hexdigest(),'question':question}
                            for question in list(catalog)[:10]]
                    draft=edu.extract_image(data,rt.call,known_questions=shared+list(known_questions or []),compact=class_batch)
                    if not draft['records']:
                        raise ValueError('此页没有识别到题目。可检查原页，或用文字补充题目。' if self_study
                                         else '没有提取到可批改的题目，请检查是否同页含有题干及答题区域。')
                draft['filename']=name
                rt.keep_image(data)
                queue['drafts'][image_hash]=draft
                progress.progress(len(queue['drafts'])/len(pages))
            except UsageLimitError as exc:
                queue['failed'][image_hash]=str(exc)
                break
            except (RuntimeError,ValueError) as exc:
                queue['failed'][image_hash]=str(exc)
        rt.persist()
    drafts=list(queue['drafts'].values())
    if pages:
        st.caption(f'已识别 {len(drafts)} / {len(pages)} 页。再次点击会继续识别未完成页，除非选择重新识别。')
    for image_hash,error in queue['failed'].items():
        st.warning(pages[image_hash][0]+'：'+error)
    if not rt.ready():
        st.info('AI 服务尚未启用，仍可保存文本材料。')
    flat=[]
    if drafts:
        choice=st.selectbox('查看识别草稿',range(len(drafts)),format_func=lambda i:drafts[i]['filename'],key=prefix+'_draft_preview')
        with st.expander('转写原文 · '+drafts[choice]['filename'],expanded=not class_batch):
            st.text(drafts[choice]['transcription'])
            for warning in drafts[choice]['warnings']:
                st.warning(warning)
    for draft in drafts:
        flat.extend(dict(row,steps='\n'.join(row['steps']),image_ref=draft['image_ref']) for row in draft['records'])
    if not flat:
        if drafts:
            st.warning('没有提取出完整题目；请裁剪或补全条件，没有生成替代答案。')
        return []
    st.warning('这是识别草稿，请核对题目、条件和解答后再保存。' if self_study else '这是模型草稿。未知编号必须人工确认，不能猜配学生。对照原图后再保存。')
    frame=pd.DataFrame(flat)
    for column in ('question_type','parent_question_no','subquestion_no'):
        if column not in frame:frame[column]='未分类' if column=='question_type' else ''
    frame=frame[['student_id','question_no','question_type','parent_question_no','subquestion_no','topic','question','steps','answer','image_ref']]
    if student_id:
        if self_study:frame['student_id']=student_id
        else:frame.loc[frame['student_id']=='','student_id']=student_id
    key=prefix+'_draft_'+digest(drafts)[:12]
    edited=st.data_editor(frame,hide_index=True,width='stretch',key=key,disabled=['image_ref'],num_rows='dynamic',
        column_config={'image_ref':None,'student_id':None if self_study else st.column_config.TextColumn('学生编号'),'question_type':st.column_config.SelectboxColumn('题型',options=['未分类']+edu.QUESTION_TYPES),
                       'parent_question_no':'大题号','subquestion_no':'小问号','question':st.column_config.TextColumn('题目与条件',width='large'),
                       'steps':st.column_config.TextColumn('原始步骤 · 可编辑',width='large')})
    incomplete=len(drafts)<len(pages) or bool(queue['errors'])
    allow_partial=st.checkbox('仅保存已识别页面，剩余页面另行处理',key=key+'_partial') if incomplete and (class_batch or attached) else True
    confirmed=st.checkbox('我已核对题目、条件和作答内容。' if self_study else '我已核对原图、学生归属、题目和作答。',key=key+'_confirmed')
    results=[]
    if st.button('确认校对并保存材料',disabled=not(confirmed and allow_partial),key=prefix+'_save_ocr'):
        try:
            rows=edited.fillna('').to_dict('records')
            if not rows:
                raise ValueError('至少保留一道完整题目。重复或多余行可删除；跨页步骤请合并到对应题目后再确认。')
            for row in rows:
                edu.normalize_submission(row,allow_unanswered=allow_unanswered)
                draft=next((d for d in drafts if d['image_ref']==row['image_ref']),None)
                if draft is None:
                    raise ValueError('新增行没有关联原图，请用文本入口补充题目，或编辑已有图片行。')
                row['transcription']=draft['transcription']
            if on_save:
                results=on_save(rows)
            else:
                for row in rows:
                    results.append(rt.add(row,'self_study' if self_study else 'image_confirmed',row['image_ref'],row['transcription'],allow_unanswered=allow_unanswered))
            st.success('已保存 '+str(len(results))+' 道题。')
        except (ValueError,OSError) as exc:
            st.error(str(exc))
    return results

def analyze(rt,items,force=False):
    progress=st.progress(0,text='准备逐题分析…')
    for i,sub in enumerate(items):
        with st.spinner('分析 '+sub['student_id']+' / '+(sub['question_no'] or sub['topic'])):
            result=edu.analyze_submission(sub,rt.call,force)
        rt.persist()
        progress.progress((i+1)/len(items),text=f'已处理 {i+1}/{len(items)}')
        if result['status']=='failed':
            st.error(result['error'])
            if result.get('error_type')=='UsageLimitError':
                st.info('其他题目继续等待，已成功的结果会复用。')
                break

def source_panel(rt,sub,show_student=True,*,show_transcription=True):
    image=rt.image(sub.get('image_ref'))
    if image:
        st.image(image,width=480)
    elif sub.get('image_ref'):
        st.info('原图不在本会话中，请保留匿名原图。')
    st.caption((sub['student_id']+' / ' if show_student else '')+(sub['question_no'] or '原始题目'))
    message(sub['question'])
    for i,line in enumerate(sub['steps'],1):
        st.text(f'{i:02d}  {line}')
    st.text('最终答案：'+(sub['answer'] or '未提供'))
    if show_transcription and sub.get('transcription') and show_student:
        with st.expander('完整转写与图像指纹'):
            st.text(sub['transcription'])
            st.code(sub['image_ref'])

def render(page,root,shared_mode,api_key=None):
    from ui.teacher import teacher
    from ui.student import student,profiles,records
    rt=Runtime(root,shared_mode,api_key)
    if any(s.get('source') in ('constructed_examples','live_constructed_fixture') for s in rt.w['submissions']):
        st.caption('当前工作区包含构造匿名材料。真实 API 响应、测试操作和真实课堂效果必须分别判断。')
    if page==PAGES[0]:
        teacher(rt)
    elif page==PAGES[1]:
        student(rt)
    elif page==PAGES[2]:
        profiles(rt)
    else:
        records(rt)
    st.caption('单机比赛演示 · 匿名角色切换不是账号身份认证；公开多人权限尚未实现。')

