"""Official DeepTutor API plus a scoped MindTrace adapter, not another Agent."""
import asyncio
from contextlib import suppress
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path

os.environ['MINDTRACE_HEADLESS']='1'
from integrations.deeptutor.runtime import configure_home,user_scope,provision,open_lesson,record_learning_event
ROOT=Path(__file__).resolve().parents[2]
configure_home(os.getenv('DEEPTUTOR_HOME',str(ROOT/'.local_data'/'deeptutor')))

from fastapi import APIRouter,HTTPException,Request,Response
from pydantic import BaseModel,ConfigDict,Field
from starlette.responses import JSONResponse
from deeptutor.api.main import app
from deeptutor.services.auth import create_token,decode_token
from core.tutor_bridge import BridgeStore,source,student_records,UPSTREAM_COMMIT
from core import classroom as c,collaboration as collab,learning_records as learning,review_scheduler as fsrs
from core import tutor_learning

bridge=BridgeStore(Path(os.environ['DEEPTUTOR_HOME'])/'mindtrace-bridge.sqlite3')
router=APIRouter(prefix='/api/mindtrace')
_opening=asyncio.Lock()


class Payload(BaseModel):model_config=ConfigDict(extra='forbid')
class Ticket(Payload):submission_id:str|None=Field(default=None,max_length=100)
class Exchange(Payload):ticket:str=Field(min_length=20,max_length=100)
class Open(Payload):submission_id:str=Field(max_length=100)
class ReviewUnit(Open):objective:str=Field(default='独立重做',max_length=30)
class StartReview(Payload):unit_id:str=Field(max_length=100)
class ReviewAttempt(Payload):
    steps:list[str]=Field(max_length=30)
    answer:str=Field(max_length=2000)
    helped:bool=False
class ReviewRating(Payload):
    attempt_id:str=Field(max_length=100)
    rating:int=Field(strict=True,ge=1,le=4)
class Correction(Open):
    expected_source_revision:str=Field(max_length=100)
    expected_fingerprint:str
    expected_reference_revision:str|None=None
    expected_grading_revision:str|None=None
    steps:list[str]=Field(max_length=30)
    answer:str=Field(max_length=2000)
    command_id:str=Field(min_length=1,max_length=100)
    independent:bool=True
    hint_used:bool=False
    answer_revealed:bool=False


def binding(request):
    try:return bridge.principal(request.cookies.get('mt_session',''))
    except ValueError:raise HTTPException(401,'请从学生课堂重新进入。') from None


@router.post('/tickets')
async def ticket(body:Ticket,request:Request):
    bearer=request.headers.get('Authorization','')
    if not bearer.startswith('Bearer '):raise HTTPException(401,'请连接学生课堂。')
    try:token=bridge.ticket(bearer[7:],body.submission_id)
    except (ValueError,OSError):raise HTTPException(403,'学生身份或题目归属无效。') from None
    return {'ticket':token,'expires_in':90}


@router.post('/connect')
async def exchange(body:Exchange,response:Response):
    try:
        record,browser=bridge.exchange(body.ticket)
        async with _opening:
            record=await asyncio.to_thread(provision,bridge,record)
    except (ValueError,OSError):raise HTTPException(401,'学习入口已失效，请从课堂重新进入。') from None
    secure=os.getenv('MINDTRACE_TUTOR_SECURE_COOKIE')=='1'
    for key,value in [('dt_token',create_token(record['username'],'student',record['dt_user_id'])),('mt_session',browser)]:
        response.set_cookie(key,value,max_age=86400,httponly=True,secure=secure,samesite='lax',path='/')
    response.headers['Cache-Control']='no-store'
    return {'ok':True,'submission_id':record.get('submission_id')}


@router.get('/me')
async def me(request:Request):
    record=binding(request)
    w=await asyncio.to_thread(c.load,collab._folder(record['class_id'])/'workspace.json')
    return {'student_id':record['student_id'],'notebook':student_records(record),
        'profile':learning.profile(w,record['student_id']),
        'due':[{'unit_id':r['unit']['id'],'submission_id':r['unit']['submission_id'],
                'objective':r['unit']['objective'],'due':r['due'].isoformat()} for r in fsrs.due(w,record['student_id'])],
        'engine':'official-deeptutor','upstream_commit':UPSTREAM_COMMIT}


@router.get('/reviews')
async def review_units(request:Request):
    return await asyncio.to_thread(tutor_learning.reviews,binding(request),bridge)


@router.post('/review-units')
async def add_review_unit(body:ReviewUnit,request:Request):
    try:return await asyncio.to_thread(tutor_learning.add_review,binding(request),body.submission_id,body.objective)
    except (ValueError,StopIteration):raise HTTPException(409,'无法加入复习，请刷新题目后重试。') from None


@router.post('/review-runs')
async def begin_review(body:StartReview,request:Request):
    try:return await asyncio.to_thread(tutor_learning.start_review,bridge,binding(request),body.unit_id)
    except (ValueError,StopIteration):raise HTTPException(409,'复习题目已更新或不可用，请刷新计划。') from None


@router.post('/review-runs/{run_id}/attempt')
async def review_attempt(run_id:str,body:ReviewAttempt,request:Request):
    try:
        record=binding(request)
        result=await asyncio.to_thread(tutor_learning.submit_review,bridge,record,run_id,body.steps,body.answer,helped=body.helped)
        await record_learning_event(record,'mindtrace_review_attempt',
            {'attempt_id':result['attempt_id'],'independent':result['independent'],
             'assessment_id':(result['assessment'] or {}).get('id'),'status':'submitted_not_mastery'})
        return result
    except (ValueError,StopIteration):raise HTTPException(409,'无法提交：题目依据已变化、复习已过期或作答无效。') from None


@router.post('/review-runs/{run_id}/rating')
async def review_rating(run_id:str,body:ReviewRating,request:Request):
    try:
        record=binding(request)
        result=await asyncio.to_thread(tutor_learning.rate_review,bridge,record,run_id,body.attempt_id,body.rating)
        await record_learning_event(record,'mindtrace_fsrs_review',{'attempt_id':body.attempt_id,**result})
        return result
    except (ValueError,StopIteration):raise HTTPException(409,'尚不能更新复习计划：请先取得可靠核验；提示后作答不能记为回忆成功。') from None


@router.get('/review-runs/{run_id}/result')
async def review_result(run_id:str,request:Request):
    try:return await asyncio.to_thread(tutor_learning.review_result,bridge,binding(request),run_id)
    except (ValueError,StopIteration):raise HTTPException(409,'该次复习不存在、已过期或题目依据已更新。') from None


@router.post('/open')
async def open_source(body:Open,request:Request):
    record=binding(request)
    bridge.mark_assisted(record['id'],body.submission_id)
    try:
        async with _opening:
            result=await open_lesson(bridge,record,body.submission_id)
    except (ValueError,StopIteration):raise HTTPException(404,'该作答不存在或不属于你。') from None
    return {'session_id':result['session_id'],'path_id':result['path_id'],
            'route':'/learning/mastery/'+result['path_id']+'/sessions/'+result['session_id']}


@router.get('/source/{submission_id}')
async def get_source(submission_id:str,request:Request):
    try:
        record=binding(request);result=source(record,submission_id)
        bridge.mark_assisted(record['id'],submission_id)
        return result
    except (ValueError,StopIteration):raise HTTPException(404,'该题目不存在。') from None


@router.get('/session/{session_id}')
async def session_source(session_id:str,request:Request):
    record=binding(request);lesson=bridge.by_session(record['id'],session_id)
    if not lesson:return {'source':None}
    current=source(record,lesson['submission_id'])
    bridge.mark_assisted(record['id'],lesson['submission_id'])
    return {'source':current,'stale':current['source_revision']!=lesson['revision']}


@router.post('/corrections')
async def correction(body:Correction,request:Request):
    record=binding(request)
    def apply(w):
        sub=learning.owned_submission(w,body.submission_id,record['student_id'])
        if (source(record,body.submission_id,w)['source_revision']!=body.expected_source_revision
            or sub['fingerprint']!=body.expected_fingerprint or sub.get('reference_revision')!=body.expected_reference_revision
            or sub.get('grading_revision')!=body.expected_grading_revision):
            raise ValueError('题目或评分依据已更新，请重新打开。')
        result=learning.submit_correction(w,sub['id'],record['student_id'],body.steps,body.answer,
            command_id=body.command_id,independent=False,hint_used=True,
            answer_revealed=True)
        if learning.latest_assessment(w,result) is None:learning.compare_correction(w,result['id'])
        return result
    try:
        from core.background import configured_repository
        path=collab._folder(record['class_id'])/'workspace.json';w=c.load(path);repo=configured_repository()
        if repo:_,attempt=repo.mutate(w['id'],apply)
        else:
            from core.storage import LOCK
            with LOCK:
                w=c.load(path);attempt=apply(w);c.save(w,path)
    except (ValueError,StopIteration):raise HTTPException(409,'订正依据已变化或内容无效，请重新打开原题。') from None
    await record_learning_event(record,'mindtrace_assisted_correction',
        {'attempt_id':attempt['id'],'submission_id':body.submission_id,'independent':False,'status':'submitted_not_mastery'})
    return {'attempt_id':attempt['id'],'message':'订正已回传，教师端可查看。'}


@router.get('/health')
async def health():
    return {'engine':'official-deeptutor','commit':UPSTREAM_COMMIT,
            'tutor_model_configured':bool(os.getenv('MINDTRACE_TUTOR_API_KEY')),
            'fsrs_version':fsrs.VERSION,'original_grades_owner':'mindtrace'}


class StudentBoundary:
    """Pair native JWT with revocable MindTrace grant on HTTP and WebSocket."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type'] not in ('http','websocket'):return await self.app(scope,receive,send)
        path=scope.get('path','');public=path in ('/api/mindtrace/tickets','/api/mindtrace/connect','/api/mindtrace/health')
        if public:return await self.app(scope,receive,send)
        cookies=SimpleCookie();cookies.load(dict(scope.get('headers',[])).get(b'cookie',b'').decode('latin-1'))
        try:
            principal=bridge.principal(cookies['mt_session'].value)
            payload=decode_token(cookies['dt_token'].value)
            if payload is None or payload.user_id!=principal['dt_user_id']:raise ValueError('Invalid principal')
        except (ValueError,KeyError):
            if path=='/api/auth/status':
                return await JSONResponse({'enabled':True,'authenticated':False,'username':None,'is_admin':False,'multi_user':True})(scope,receive,send)
            if scope['type']=='websocket':return await send({'type':'websocket.close','code':4401})
            return await JSONResponse({'detail':'请从学生课堂进入学习空间。'},status_code=401)(scope,receive,send)
        if scope['type']=='http' and scope.get('method') not in ('GET','HEAD','OPTIONS') and (
            path.startswith(('/api/settings','/api/config','/api/admin','/api/users','/api/mcp','/api/cli-apps','/api/plugins'))
            or path.startswith('/api/auth/') and path!='/api/auth/logout'):
            return await JSONResponse({'detail':'课堂教学服务不开放此配置操作。'},status_code=403)(scope,receive,send)
        async def checked_receive():
            while True:
                message=await receive()
                if scope['type']!='websocket' or message.get('type')!='websocket.receive':return message
                try:
                    bridge.principal(cookies['mt_session'].value)
                except ValueError:
                    await send({'type':'websocket.close','code':4401})
                    return {'type':'websocket.disconnect','code':4401}
                try:
                    command=json.loads(message.get('text','{}'))
                    if command.get('type') in ('message','start_turn') and command.get('session_id'):
                        lesson=bridge.by_session(principal['id'],command['session_id'])
                        if lesson:bridge.mark_assisted(principal['id'],lesson['submission_id'])
                        if lesson and source(principal,lesson['submission_id'])['source_revision']!=lesson['revision']:
                            await send({'type':'websocket.send','text':json.dumps({'type':'protocol_error','protocol_version':'2.0',
                                'error_code':'source_changed','message':'教师已更新本题依据，请从我的错题重新打开。','retryable':False})})
                            continue
                except (ValueError,KeyError):pass
                return message
        await self.app(scope,checked_receive,send)


app.include_router(router)
app.add_middleware(StudentBoundary)

