"""Scoped API over the same domain services and durable repository."""
from copy import deepcopy
from pathlib import Path
from fastapi import FastAPI,Depends,HTTPException,Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field

from core import classroom as c,collaboration as collab,learning_records as learning,review_scheduler as review
from core.background import configured_repository
from core.repository import ConflictError

app=FastAPI(title='MindTrace 循理 AI',version='0.2.0',docs_url=None,redoc_url=None)
bearer=HTTPBearer(auto_error=False)


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class CreateClass(Input):
    name:str=Field(min_length=1,max_length=80)
    number_demo:bool=False

class Correction(Input):
    submission_id:str=Field(max_length=100)
    expected_fingerprint:str=Field(max_length=100)
    expected_reference_revision:str|None=None
    expected_grading_revision:str|None=None
    parent_id:str|None=None
    steps:list[str]=Field(max_length=30)
    answer:str=Field(max_length=2000)
    command_id:str=Field(min_length=1,max_length=100)
    independent:bool=True
    hint_used:bool=False
    answer_revealed:bool=False
    origin:str='correction'
    attachment_refs:list[str]=Field(default_factory=list,max_length=12)

class ReviewCorrection(Input):
    verdict:str
    note:str=Field(min_length=1,max_length=2000)
    command_id:str=Field(min_length=1,max_length=100)

class Unit(Input):
    submission_id:str=Field(max_length=100)
    objective:str='独立重做'

class ReviewLog(Input):
    unit_id:str=Field(max_length=100)
    attempt_id:str=Field(max_length=100)
    rating:int=Field(ge=1,le=4,strict=True)
    command_id:str=Field(min_length=1,max_length=100)
    duration_ms:int|None=Field(default=None,ge=0,le=86400000)

class Sync(Input):
    base:dict
    after:dict

class Invite(Input):
    student_id:str=Field(min_length=1,max_length=80)


@app.middleware('http')
async def bounded_body(request:Request,call_next):
    # Reads and bounds actual body, including chunked requests without Content-Length.
    size=0;parts=[]
    async for chunk in request.stream():
        size+=len(chunk)
        if size>32*1024*1024:return Response('Request too large',status_code=413)
        parts.append(chunk)
    request._body=b''.join(parts)
    return await call_next(request)


def access(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
    if credentials is None:raise HTTPException(401,'请连接课堂。')
    try:return collab.resolve(credentials.credentials)
    except (ValueError,OSError):raise HTTPException(401,'课堂连接已失效。') from None


def teacher(a=Depends(access)):
    if a['role']!='teacher':raise HTTPException(403,'此操作仅对教师开放。')
    return a


def student(a=Depends(access)):
    if a['role']!='student':raise HTTPException(403,'请使用学生学习码。')
    return a


def workspace(a):return c.load(collab._folder(a['class_id'])/'workspace.json')


def mutate(a,operation):
    repo=configured_repository()
    if repo is None:raise HTTPException(503,'持久存储尚未配置。')
    w=workspace(a)
    try:
        _,result=repo.mutate(w['id'],operation)
        return result
    except ConflictError:raise HTTPException(409,'记录已更新，请刷新。') from None
    except (ValueError,StopIteration):raise HTTPException(422,'记录或操作无效，请刷新后核对。') from None


@app.get('/health')
def health():
    from core.ai import ai_ready
    repo=configured_repository()
    return {'status':'ok','persistent':repo is not None,'worker_available':repo.worker_available() if repo else False,'model_configured':ai_ready()}


@app.post('/classrooms')
def create_class(data:CreateClass,request:Request):
    try:
        code=collab.create(data.name,number_demo=data.number_demo,creator_id=(request.client.host if request.client else 'api'))
        return {'code':code}
    except (ValueError,RuntimeError,OSError):raise HTTPException(429,'暂时无法创建课堂，请稍后重试。') from None


@app.get('/access')
def get_access(a=Depends(access)):return {k:v for k,v in a.items() if k!='code'}


@app.get('/workspace')
def get_workspace(a=Depends(access)):
    w=workspace(a)
    return w if a['role']=='teacher' else collab.student_view(w,a['student_id'])


@app.post('/workspace/sync')
def sync(data:Sync,a=Depends(access)):
    # Transitional command adapter: reuse the existing scope checks and merge;
    # typed commands below are preferred for all new functionality.
    try:
        current=workspace(a)
        if data.base.get('id')!=current['id'] or data.after.get('id')!=current['id']:
            raise ValueError('工作区不匹配。')
        if a['role']=='student':
            visible=collab.student_view(current,a['student_id'])
            # Reject fabricated bases that omit teacher records before merging.
            if data.base.get('storage_version')==current['storage_version'] and data.base!=visible:
                raise ValueError('学生记录基线无效。')
            known={s['id'] for s in current['submissions']}
            repo=configured_repository()
            for sub in data.after.get('submissions',[]):
                if sub.get('id') not in known and sub.get('image_ref') and (
                    repo is None or not repo.owns_asset(current['id'],sub['image_ref'],a['student_id'])):
                    raise ValueError('图片不属于该学生。')
            old_attempts={attempt['id'] for attempt in current.get('correction_attempts',[])}
            for attempt in data.after.get('correction_attempts',[]):
                if attempt.get('id') in old_attempts:continue
                if any(repo is None or not repo.owns_asset(current['id'],ref,a['student_id']) for ref in attempt.get('attachment_refs',[])):
                    raise ValueError('订正图片不属于该学生。')
        after=deepcopy(data.after)
        collab.save(a['code'],data.base,after)
        return after
    except (ValueError,OSError):raise HTTPException(409,'记录已更新或超出操作范围，请刷新后重试。') from None


@app.post('/students/invite')
def invite(data:Invite,a=Depends(teacher)):
    try:return {'code':collab.invite(a['code'],data.student_id)}
    except (ValueError,OSError):raise HTTPException(422,'请先保存该学生的作业。') from None


@app.post('/assignments/{batch_id}/grade')
def grade(batch_id:str,a=Depends(teacher)):
    w=workspace(a)
    if not any(b['id']==batch_id for b in w['batches']):raise HTTPException(404,'作业不存在。')
    repo=configured_repository()
    if repo is None:raise HTTPException(503,'后台处理尚未配置。')
    return {'queued':repo.enqueue_batch(w['id'],batch_id,retry_failed=True)}


@app.get('/assignments/{batch_id}/jobs')
def jobs(batch_id:str,a=Depends(teacher)):
    repo=configured_repository()
    if repo is None:raise HTTPException(503,'后台处理尚未配置。')
    return repo.jobs(workspace(a)['id'],batch_id)


@app.post('/assignments/{batch_id}/cancel')
def cancel(batch_id:str,a=Depends(teacher)):
    repo=configured_repository()
    if repo is None:raise HTTPException(503,'后台处理尚未配置。')
    repo.cancel_batch(workspace(a)['id'],batch_id)
    return {'cancelled':True}


@app.post('/corrections')
def correction(data:Correction,a=Depends(student)):
    from core.learning_service import submit
    try:return submit(a['code'],data.model_dump())
    except (ValueError,StopIteration):raise HTTPException(422,'记录或操作无效，请刷新后核对。') from None


@app.post('/corrections/{attempt_id}/review')
def correction_review(attempt_id:str,data:ReviewCorrection,a=Depends(teacher)):
    return mutate(a,lambda w:learning.assess_correction(w,attempt_id,data.verdict,data.note,command_id=data.command_id))


@app.post('/corrections/{attempt_id}/compare')
def compare_correction(attempt_id:str,a=Depends(teacher)):
    return mutate(a,lambda w:learning.compare_correction(w,attempt_id))


@app.get('/learning/profile')
def profile(a=Depends(student)):return learning.profile(workspace(a),a['student_id'])


@app.post('/learning/units')
def unit(data:Unit,a=Depends(student)):
    return mutate(a,lambda w:review.add_unit(w,data.submission_id,a['student_id'],objective=data.objective))


@app.get('/learning/due')
def due(a=Depends(student)):
    return [{'unit':row['unit'],'due':row['due'].isoformat(),'valid_reviews':row['valid_reviews']}
            for row in review.due(workspace(a),a['student_id'])]


@app.post('/learning/reviews')
def review_log(data:ReviewLog,a=Depends(student)):
    return mutate(a,lambda w:review.record_review(w,data.unit_id,a['student_id'],data.attempt_id,
        data.rating,command_id=data.command_id,duration_ms=data.duration_ms))


@app.get('/assets/{ref}')
def asset(ref:str,a=Depends(access)):
    import re
    if not re.fullmatch(r'[a-f0-9]{64}',ref):raise HTTPException(404)
    w=workspace(a)
    visible=w if a['role']=='teacher' else collab.student_view(w,a['student_id'])
    allowed={s.get('image_ref') for s in visible['submissions']}
    allowed.update(ref for attempt in visible.get('correction_attempts',[]) for ref in attempt.get('attachment_refs',[]))
    if a['role']=='teacher':allowed.update(page['original_image'] for b in w['batches'] for m in b.get('materials',[]) for page in m['pages'])
    if ref not in allowed:raise HTTPException(404)
    data=c.read_image(ref,collab._folder(a['class_id'])/'images')
    if data is None:raise HTTPException(404)
    return Response(data,media_type='application/octet-stream',headers={'Cache-Control':'private, no-store'})


@app.put('/assets/{ref}')
async def upload_asset(ref:str,request:Request,a=Depends(access)):
    import hashlib
    import re
    from PIL import Image
    import io
    data=await request.body()
    if len(data)>8*1024*1024 or not re.fullmatch(r'[a-f0-9]{64}',ref) or hashlib.sha256(data).hexdigest()!=ref:
        raise HTTPException(422,'图片大小或校验不符合要求。')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width*image.height>40_000_000:raise ValueError('图片分辨率过大。')
            image.verify()
    except Exception:raise HTTPException(422,'不是有效图片。') from None
    repo=configured_repository();w=workspace(a)
    if repo is None:raise HTTPException(503,'材料存储尚未配置。')
    try:
        repo.stage_asset(w['id'],ref,len(data),owner=a['student_id'] or 'teacher')
        c.attach_image(data,collab._folder(a['class_id'])/'images')
        repo.ready_asset(w['id'],ref)
    except (ValueError,OSError):raise HTTPException(422,'材料保存失败或课堂存储额度已满。') from None
    return {'ref':ref}


@app.put('/originals/{ref}')
async def upload_original(ref:str,request:Request,a=Depends(teacher)):
    import hashlib
    import re
    data=await request.body()
    if len(data)>24*1024*1024 or not data.startswith(b'%PDF-') or not re.fullmatch(r'[a-f0-9]{64}',ref) or hashlib.sha256(data).hexdigest()!=ref:
        raise HTTPException(422,'PDF大小或校验不符合要求。')
    repo=configured_repository();w=workspace(a)
    if repo is None:raise HTTPException(503,'材料存储尚未配置。')
    try:
        repo.stage_asset(w['id'],ref,len(data),owner='teacher',kind='pdf')
        c.attach_image(data,collab._folder(a['class_id'])/'images'/'originals')
        repo.ready_asset(w['id'],ref,kind='pdf')
    except (ValueError,OSError):raise HTTPException(422,'材料保存失败或课堂存储额度已满。') from None
    return {'ref':ref}


@app.get('/originals/{ref}')
def original(ref:str,a=Depends(teacher)):
    import re
    if not re.fullmatch(r'[a-f0-9]{64}',ref):raise HTTPException(404)
    w=workspace(a)
    allowed={page['original_file'] for b in w['batches'] for m in b.get('materials',[]) for page in m['pages']}
    if ref not in allowed:raise HTTPException(404)
    data=c.read_image(ref,collab._folder(a['class_id'])/'images'/'originals')
    if data is None:raise HTTPException(404)
    return Response(data,media_type='application/pdf',headers={'Cache-Control':'private, no-store'})
