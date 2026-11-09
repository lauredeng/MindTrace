"""Single-instance classroom collaboration with scoped bearer access codes.
No API credentials live here. Put the classroom directory on persistent storage.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,hmac,json,os,re,secrets,tempfile
from core import classroom as c,storage,education as e
from core.limits import UsageLimiter, Limits, UsageLimitError
from core.settings import integer_setting
from core.uploads import school_number

DENIED='课堂访问码无效或已失效。'
MISSING=object()
CREATION_LIMITER=UsageLimiter()
CREATION_LIMITS=Limits(session_minute=2,session_day=5,global_minute=10,global_day=50,daily_units=50,concurrent=1)

def root_dir():
    return Path(os.getenv('MINDTRACE_CLASSROOM_DIR',str(storage.DATA_DIR/'classrooms')))

def _folder(class_id,root=None):
    if not re.fullmatch(r'[a-f0-9]{32}',class_id):raise ValueError(DENIED)
    return (Path(root) if root else root_dir())/class_id

def _hash(token):return hashlib.sha256(token.encode()).hexdigest()

def _write_meta(folder,meta):
    folder.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.access-',dir=folder)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(meta,f,ensure_ascii=False)
        os.replace(name,folder/'access.json')
    finally:
        if Path(name).exists():Path(name).unlink()

def create(name,root=None,*,creator_id='server-script',number_demo=False):
    name=e.text(name,80,'课堂名称');class_id=secrets.token_hex(16);token=secrets.token_urlsafe(32)
    folder=_folder(class_id,root)
    with CREATION_LIMITER.request(creator_id,1,CREATION_LIMITS):
        with storage.LOCK:
            parent=folder.parent
            maximum=integer_setting('MINDTRACE_CLASSROOM_MAX',1000)
            if parent.exists() and sum(1 for child in parent.iterdir() if child.is_dir())>=maximum:
                raise UsageLimitError('课堂存储数量已达上限，请联系管理员；已有课堂仍可连接。')
            folder.mkdir(parents=True,exist_ok=False)
            _write_meta(folder,{'name':name,'teacher_hash':_hash(token),'students':{},'number_demo':bool(number_demo),'created_at':c.now()})
            c.save(c.new_workspace(),folder/'workspace.json')
    return class_id+'.'+token

def has_student_number(w,number):
    roster=w.get('student_roster',[])
    if roster:return number in roster
    return any(s['student_id']==number and s.get('batch_id') and s.get('source')!='self_study'
               for s in w['submissions'])


def demo_code(class_id,number):
    if not re.fullmatch(r'[a-f0-9]{32}',class_id.strip()):
        raise ValueError('演示课堂码无效。')
    return class_id.strip()+'.'+school_number(number)


def resolve(code,root=None):
    if not isinstance(code,str) or len(code)>130 or code.count('.')!=1:raise ValueError(DENIED)
    class_id,token=code.strip().split('.')
    demo_student=bool(re.fullmatch(r'[0-9]{1,32}',token))
    if not demo_student and not re.fullmatch(r'[A-Za-z0-9_-]{40,64}',token):raise ValueError(DENIED)
    folder=_folder(class_id,root)
    try:meta=json.loads((folder/'access.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):raise ValueError(DENIED) from None
    if (not isinstance(meta,dict) or not isinstance(meta.get('name'),str) or not isinstance(meta.get('teacher_hash'),str)
        or not re.fullmatch(r'[a-f0-9]{64}',meta['teacher_hash']) or not isinstance(meta.get('students'),dict)
        or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in meta['students'].items())):
        raise ValueError(DENIED)
    number_demo=meta.get('number_demo') is True
    if demo_student:
        if not number_demo or not has_student_number(c.load(folder/'workspace.json'),token):
            raise ValueError(DENIED)
        role,sid='student',token
    else:
        digest=_hash(token)
        if hmac.compare_digest(meta['teacher_hash'],digest):role,sid='teacher',None
        else:
            sid=next((sid for sid,hashed in meta['students'].items() if hmac.compare_digest(hashed,digest)),None)
            if sid is None:raise ValueError(DENIED)
            role='student'
    return {'class_id':class_id,'name':meta['name'],'role':role,'student_id':sid,'code':code.strip(),
            'number_demo':number_demo}

def invite(teacher_code,student_id,root=None):
    with storage.LOCK:
        access=resolve(teacher_code,root)
        if access['role']!='teacher':raise ValueError('只有教师可以发放学习码。')
        folder=_folder(access['class_id'],root);w=c.load(folder/'workspace.json')
        if not any(s['student_id']==student_id for s in w['submissions']):raise ValueError('请先保存该学生的作业材料。')
        meta=json.loads((folder/'access.json').read_text(encoding='utf-8'));token=secrets.token_urlsafe(32)
        meta['students'][student_id]=_hash(token);_write_meta(folder,meta)
        return access['class_id']+'.'+token

def student_view(w,sid):
    view=deepcopy(w)
    view.pop('student_roster',None)
    own=[s for s in w['submissions'] if s['student_id']==sid];ids={s['id'] for s in own}
    view['submissions']=[e.student_material(w,s) for s in own]
    view['notebook']=[n for n in view['notebook'] if n['student_id']==sid]
    visible_images={s['id']:s.get('image_ref') for s in view['submissions']}
    for item in view['notebook']:item['image_ref']=visible_images.get(item['submission_id'])
    entries={n['id'] for n in view['notebook']}
    view['book_events']=[x for x in view['book_events'] if x['entry_id'] in entries]
    for event in view['book_events']:
        if isinstance(event.get('previous'),dict):event['previous']['image_ref']=None
    view['reviews']=[x for x in view['reviews'] if x['submission_id'] in ids]
    for key in ('tasks','learning','attempts','study_sessions'):
        view[key]=[x for x in view[key] if x.get('student_id')==sid]
    # Class-wide lists, scores, request metadata and public images never reach student UI.
    view['batches']=[{k:deepcopy(b[k]) for k in ('id','name','created_at','status') if k in b} |
        {'submission_ids':[rid for rid in b['submission_ids'] if rid in ids],
         'questions':[deepcopy(q) for q in b['questions'] if q['id'] in {s.get('question_id') for s in own}]}
        for b in w['batches'] if any(rid in ids for rid in b['submission_ids'])]
    view['usage']=[];view['events']=[]
    return view

def load(code,root=None):
    with storage.LOCK:
        access=resolve(code,root)
        w=c.load(_folder(access['class_id'],root)/'workspace.json')
        return w if access['role']=='teacher' else student_view(w,access['student_id'])

def _merge(base,ours,theirs):
    if ours==base:return deepcopy(theirs)
    if theirs==base or ours==theirs:return deepcopy(ours)
    if isinstance(base,dict) and isinstance(ours,dict) and isinstance(theirs,dict):
        result={}
        for key in base.keys()|ours.keys()|theirs.keys():
            b=base.get(key,MISSING);o=ours.get(key,MISSING);t=theirs.get(key,MISSING)
            if o==b:value=t
            elif t==b or o==t:value=o
            elif key=='updated_at' and all(isinstance(v,str) for v in (b,o,t)):value=max(o,t)
            elif b is MISSING or o is MISSING or t is MISSING:raise ValueError('同一记录发生并发修改，请刷新课堂后重试。')
            else:value=_merge(b,o,t)
            if value is not MISSING:result[key]=deepcopy(value)
        return result
    if all(isinstance(x,list) and all(isinstance(r,dict) and isinstance(r.get('id'),str) for r in x) for x in (base,ours,theirs)):
        maps=[{r['id']:r for r in x} for x in (base,ours,theirs)]
        merged=_merge(*maps)
        order=list(dict.fromkeys([r['id'] for r in theirs]+[r['id'] for r in ours]))
        return [merged[k] for k in order if k in merged]
    raise ValueError('同一记录发生并发修改，请刷新课堂后重试。')

def _student_changes(base,after,sid):
    for key in ('schema_version','id','batches','reviews','tasks','student_roster'):
        if after.get(key)!=base.get(key):raise ValueError('学生不能修改教师记录。')
    for key in ('submissions','notebook','learning','attempts','study_sessions'):
        old={r['id']:r for r in base[key]};new={r['id']:r for r in after[key]}
        if not old.keys()<=new.keys():raise ValueError('原始记录不能删除。')
        for rid,row in new.items():
            if row.get('student_id')!=sid:raise ValueError('只能保存自己的学习记录。')
            if key=='submissions':
                if rid not in old and row.get('source')!='self_study':raise ValueError('学生只能新增自主学习题目。')
                if rid in old:
                    immutable=(set(old[rid])|set(row))-{'analyses','quick_checks','solutions'}
                    if any(row.get(k)!=old[rid].get(k) for k in immutable):raise ValueError('不能改写原始题目或作答。')
    own_ids={row['id'] for row in after['submissions']}
    for key in ('notebook','learning','attempts','study_sessions'):
        for row in after[key]:
            if row.get('submission_id') and row['submission_id'] not in own_ids:raise ValueError('学习记录必须关联自己的原始作答。')
            if any(rid not in own_ids for rid in row.get('source_ids',[])):raise ValueError('原始来源归属无效。')
    entries={n['id'] for n in after['notebook']}
    if any(x.get('entry_id') not in entries for x in after['book_events']):raise ValueError('错题记录归属无效。')

def adopt(target, source):
    """Receive merged state while preserving references used by an active batch.

    ID-based lists keep existing record objects; plain value lists are replaced.
    Call only after a successful save (or an explicit refresh).
    """
    if isinstance(target,dict) and isinstance(source,dict):
        for key in list(target):
            if key not in source:del target[key]
        for key,value in source.items():
            if key in target and isinstance(value,(dict,list)) and type(target[key]) is type(value):
                adopt(target[key],value)
            else:target[key]=deepcopy(value)
    elif isinstance(target,list) and isinstance(source,list):
        if all(isinstance(row,dict) and isinstance(row.get('id'),str) for row in target+source):
            existing={row['id']:row for row in target};updated=[]
            for row in source:
                item=existing.get(row['id'])
                if item is None:item=deepcopy(row)
                else:adopt(item,row)
                updated.append(item)
            target[:]=updated
        else:target[:]=deepcopy(source)


def save(code,base,after,root=None):
    """Three-way merge independent edits; reject conflicts instead of losing data."""
    with storage.LOCK:
        access=resolve(code,root);folder=_folder(access['class_id'],root)
        if access['role']=='student':_student_changes(base,after,access['student_id'])
        current=c.load(folder/'workspace.json')
        if current['id']!=after['id'] or base['id']!=after['id']:raise ValueError('课堂记录不匹配。')
        local_submissions={row['id']:row for row in after['submissions']}
        current_submissions={row['id']:row for row in current['submissions']}
        for original in base['submissions']:
            local=local_submissions.get(original['id'])
            remote=current_submissions.get(original['id'])
            if local is None or remote is None:
                continue
            fields=('analyses','quick_checks','solutions')
            if (remote['fingerprint']!=original['fingerprint'] and any(local.get(k)!=original.get(k) for k in fields)
                or local['fingerprint']!=original['fingerprint'] and any(remote.get(k)!=original.get(k) for k in fields)):
                raise ValueError('该作答的转写与分析同时发生修改，请刷新课堂后重试。')
        before=deepcopy(base);ours=deepcopy(after);theirs=deepcopy(current)
        for key in ('storage_version','revision'):
            before.pop(key,None);ours.pop(key,None);theirs.pop(key,None)
        merged=_merge(before,ours,theirs)
        merged['storage_version']=current['storage_version']
        merged['revision']=max(current['revision'],after['revision'])
        c.save(merged,folder/'workspace.json')
        visible=merged if access['role']=='teacher' else student_view(merged,access['student_id'])
        adopt(after,visible)
        return merged['storage_version']

def image_directory(code,root=None):
    access=resolve(code,root)
    return _folder(access['class_id'],root)/'images'

def version(code,root=None):return load(code,root)['storage_version']
