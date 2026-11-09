"""Bounded persisted-record checks, without changing the version-1 JSON shape."""
import re

BATCH_LIMIT = 1600


def _text(value, limit, name, empty=False):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()):
        raise ValueError('记录中的'+name+'无效，请保留原备份并检查数据。')


def _records(rows,name,limit=2000):
    if not isinstance(rows,list) or len(rows)>limit:
        raise ValueError('记录中的'+name+'格式或数量无效。')
    ids=[]
    for row in rows:
        if not isinstance(row,dict):raise ValueError('记录中的'+name+'必须是对象。')
        _text(row.get('id'),100,name+'编号');ids.append(row['id'])
    if len(set(ids))!=len(ids):raise ValueError('记录中的'+name+'编号重复。')


def _validate_materials(batch, submissions):
    from core.uploads import MAX_PDF_PAGES,MAX_PHOTOS,MAX_TEACHER_FILES,student_number
    materials=batch['materials']
    if not isinstance(materials,list) or not 1<=len(materials)<=MAX_TEACHER_FILES:
        raise ValueError('学生作业材料数量无效。')
    by_student={}
    owners={}
    for material in materials:
        if not isinstance(material,dict):raise ValueError('学生作业材料格式无效。')
        sid=material.get('student_id')
        _text(sid,80,'学生编号')
        mode=material.get('kind')
        if (sid.upper()!=student_number(sid) or sid in by_student or material.get('assignment_id')!=batch['id']
            or mode not in ('pdf','photos') or material.get('identity_status') not in ('filename','homepage','manual','file_group')):
            raise ValueError('学生作业归属无效。')
        pages=material.get('pages')
        if not isinstance(pages,list) or not 1<=len(pages)<=(MAX_PDF_PAGES if mode=='pdf' else MAX_PHOTOS):
            raise ValueError('作业页数无效。')
        by_student[sid]=pages
        file_ids=set()
        for number,page in enumerate(pages,1):
            if not isinstance(page,dict) or type(page.get('page_number')) is not int or page['page_number']!=number or page.get('recognition_status') not in ('recognized','no_work'):
                raise ValueError('原始页顺序或识别状态无效。')
            for key in ('file_id','original_file','original_image'):
                if not re.fullmatch(r'[a-f0-9]{64}',str(page.get(key,''))):
                    raise ValueError('作业原始证据引用无效。')
            fid=page['file_id']
            if (page['original_file']!=fid or owners.setdefault(fid,sid)!=sid
                or mode=='photos' and (fid in file_ids or page['original_image']!=fid)):
                raise ValueError('同一原始文件不能分配给多个学生或重复计页。')
            file_ids.add(fid)
            _text(page.get('filename'),200,'原始文件名')
            _text(page.get('transcription'),20000,'页面转写',True)
            records=page.get('recognized_records',[])
            if not isinstance(records,list) or len(records)>30 or any(not isinstance(row,dict) for row in records):
                raise ValueError('页面识别证据格式无效。')
            answers=page.get('recognized_answers',[])
            if not isinstance(answers,list) or len(answers)>40 or any(not isinstance(row,dict) for row in answers):
                raise ValueError('页面作答证据格式无效。')
            for row in records:_text(row.get('question'),4000,'识别题目')
            for row in records+answers:
                _text(row.get('answer'),2000,'识别答案',True)
                steps=row.get('steps')
                if not isinstance(steps,list) or len(steps)>30 or any(not isinstance(s,str) or len(s)>2000 for s in steps):
                    raise ValueError('页面识别步骤格式无效。')
        if mode=='pdf' and len(file_ids)!=1:
            raise ValueError('每位学生的 PDF 页面必须来自同一份文件。')
    for sid in batch['submission_ids']:
        sub=submissions[sid]
        pages=by_student.get(sub['student_id'],[])
        numbers=sub.get('source_pages')
        if (sub.get('batch_id')!=batch['id'] or not isinstance(numbers,list) or not numbers
            or any(type(n) is not int or not 1<=n<=len(pages) for n in numbers)
            or numbers!=sorted(set(numbers))
            or any(pages[n-1]['recognition_status']!='recognized' for n in numbers)
            or sub.get('image_ref')!=pages[numbers[0]-1]['original_image']):
            raise ValueError('作答未关联到本学生的有效原始页。')
    if (len({sid.casefold() for sid in by_student})!=len(by_student)
        or set(by_student)!={submissions[sid]['student_id'] for sid in batch['submission_ids']}):
        raise ValueError('存在未关联到题目的学生作业。')


def _validate_answer_keys(keys):
    if not isinstance(keys,dict) or len(keys)>BATCH_LIMIT:
        raise ValueError('作业参考答案格式或数量无效。')
    confirmed_ids=set()
    for key,entry in keys.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key) or not isinstance(entry,dict):
            raise ValueError('作业参考答案关联无效。')
        history=entry.get('history',[])
        _records(history,'参考答案修订',30)
        versions=[*history]
        if 'confirmed' in entry:versions.append(entry['confirmed'])
        if 'draft' in entry:versions.append(entry['draft'])
        for version in versions:
            if not isinstance(version,dict) or version.get('source') not in ('teacher','ai_draft','ai_confirmed'):
                raise ValueError('参考答案来源无效。')
            _text(version.get('id'),100,'参考答案版本')
            _text(version.get('answer'),2000,'参考答案')
            _text(version.get('rubric'),2000,'评分依据',True)
            _text(version.get('created_at'),100,'参考答案创建时间')
            if version is entry.get('draft'):
                if version['source']!='ai_draft':raise ValueError('参考答案草稿状态无效。')
            else:
                if version['source']=='ai_draft' or version['id'] in confirmed_ids:
                    raise ValueError('参考答案确认版本无效。')
                confirmed_ids.add(version['id'])
        if 'error' in entry:_text(entry['error'],2000,'参考答案生成状态')
    return confirmed_ids


def validate_links(data):
    """Validate canonical material and ownership; legacy optional fields stay optional."""
    submissions={row['id']:row for row in data['submissions']}
    for sub in submissions.values():
        for key,limit,empty in [('student_id',80,False),('question',4000,False),('answer',2000,True),
                                ('fingerprint',100,False),('source',100,False)]:
            _text(sub.get(key),limit,key,empty)
        steps=sub.get('steps')
        if not isinstance(steps,list) or len(steps)>30 or any(not isinstance(s,str) or len(s)>2000 for s in steps):
            raise ValueError('原始作答步骤格式无效。')
        if sum(map(len,steps))>8000:raise ValueError('原始作答步骤过长。')
        for key in ('analyses','quick_checks','solutions'):
            rows=sub.get(key,[]) if key!='analyses' else sub.get(key)
            _records(rows,key)
            if any(row.get('status') not in ('completed','failed') for row in rows):
                raise ValueError('分析记录状态无效。')
            for row in rows:
                if row['status']=='completed' and key=='analyses' and not isinstance(row.get('analysis'),dict):
                    raise ValueError('分析记录缺少有效内容。')
                if row['status']=='completed' and key=='analyses':
                    # Import at validation time: education consumes classroom IDs.
                    from core.education import validate_analysis
                    validate_analysis(row['analysis'],sub)
                if row['status']=='completed' and key=='quick_checks' and row.get('verdict') not in ('correct','incorrect','uncertain'):
                    raise ValueError('短批改记录结论无效。')
                if row['status']=='completed' and key=='solutions':
                    if not isinstance(row.get('correction'),dict) or row.get('mode') not in ('hint','steps','full'):
                        raise ValueError('解题记录内容或模式无效。')
    for key in ('reviews','tasks','learning','study_sessions','notebook'):
        for row in data.get(key,[]):
            _text(row.get('submission_id'),100,'原题关联')
            sub=submissions.get(row.get('submission_id'))
            if sub is None:raise ValueError('学习记录没有关联有效原题。')
            if key!='reviews' and row.get('student_id')!=sub['student_id']:
                raise ValueError('学习记录与原题的学生归属不一致。')
            if key=='notebook':
                if not isinstance(row.get('source_ids'),list):raise ValueError('错题来源列表无效。')
                for sid in row['source_ids']:
                    if not isinstance(sid,str) or sid not in submissions or submissions[sid]['student_id']!=row['student_id']:
                        raise ValueError('错题来源必须属于同一学生。')
                for field,limit,empty in [('question',4000,False),('original_answer',2000,True),
                                           ('correct_answer',2500,False),('primary_category',100,False),('notes',2000,True)]:
                    _text(row.get(field),limit,field,empty)
            if key=='study_sessions':
                _records(row.get('turns'), '辅导对话',80)
                _records(row.get('agent_runs',[]), '深度辅导',40)
    imported_students=set()
    imported_files=set()
    for batch in data.get('batches',[]):
        ids=batch.get('submission_ids')
        if not isinstance(ids,list) or len(ids)>BATCH_LIMIT or any(not isinstance(sid,str) or sid not in submissions for sid in ids):
            raise ValueError('作业批次关联无效。')
        _text(batch.get('name'),100,'作业名称')
        _records(batch.get('questions'),'批次题目',BATCH_LIMIT)
        if 'answer_keys' in batch:
            versions=_validate_answer_keys(batch['answer_keys'])
            if any(submissions[sid].get('reference_revision') not in versions for sid in ids
                   if submissions[sid].get('reference_revision')):
                raise ValueError('作答关联的参考答案版本无效。')
        if 'materials' in batch:
            _validate_materials(batch,submissions)
            name=batch['name'].strip().casefold()
            students={(name,m['student_id'].casefold()) for m in batch['materials']}
            files={(name,p['file_id']) for m in batch['materials'] for p in m['pages']}
            if students & imported_students or files & imported_files:
                raise ValueError('同名作业不能重复导入同一学生或原始文件。')
            imported_students.update(students)
            imported_files.update(files)
    entries={row['id'] for row in data.get('notebook',[])}
    if any(not isinstance(row.get('entry_id'),str) or row['entry_id'] not in entries for row in data.get('book_events',[])):
        raise ValueError('错题修订记录关联无效。')
