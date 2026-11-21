"""SDK adapter to unmodified official teaching, memory and learning services."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
from core.tutor_bridge import context_text, source


@contextmanager
def user_scope(binding):
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user,user_context
    user=CurrentUser(id=binding['dt_user_id'],username=binding['username'],role='student',
                     scope=scope_for_user(binding['dt_user_id'],is_admin=False))
    with user_context(user):yield


def provision(store,binding):
    from deeptutor.multi_user.identity import get_user,save_user,load_users
    from deeptutor.services.auth import hash_password
    from deeptutor.multi_user.grants import empty_grant,save_grant
    if not load_users():
        save_user('mindtrace-bootstrap-admin',hash_password(secrets.token_urlsafe(32)),role='admin')
    record=get_user(binding['username'])
    if record is None:
        record=save_user(binding['username'],hash_password(secrets.token_urlsafe(32)),role='student')
    if record['role']!='student':raise ValueError('关联账户角色无效。')
    store.bind_user(binding['id'],record['id'])
    binding=dict(binding,dt_user_id=record['id'])
    grant=empty_grant(record['id'])
    # Official deferred-provider views are grant-filtered. Registration alone
    # does not expose a tool: explicitly lend only these local adapters.
    grant.update(enabled_tools=['reason','geogebra_analysis'],
        mcp_tools=['mindtrace_source','mindtrace_math','mindtrace_learning_evidence'],cli_apps=[],exec_enabled=False)
    if configure_model():
        grant['models']['llm']=[{'profile_id':'mindtrace-teaching','model_ids':['mindtrace-teaching-model']}]
    save_grant(record['id'],grant)
    with user_scope(binding):
        from deeptutor.services.settings.interface_settings import update_ui_settings
        update_ui_settings({'language':'zh','response_language':'zh'})
    return binding


def configure_model():
    """Configure a server-side tutor profile only from explicit tutor settings.

    An OCR-only key is never silently promoted to a paid reasoning model.
    Fake provider endpoints exist only in isolated tests, never in this adapter.
    """
    from deeptutor.multi_user.model_access import admin_catalog_service
    key=os.getenv('MINDTRACE_TUTOR_API_KEY','').strip()
    if not key:return False
    base=os.getenv('MINDTRACE_TUTOR_BASE_URL','https://api.deepseek.com').rstrip('/')
    from urllib.parse import urlparse
    target=urlparse(base)
    if target.scheme!='https' or target.username or target.password or target.query or target.fragment:
        raise ValueError('教学模型服务地址必须为HTTPS。')
    model=os.getenv('MINDTRACE_TUTOR_MODEL','deepseek-flash')
    service=admin_catalog_service();catalog=service.load()
    profile={'id':'mindtrace-teaching','name':'MindTrace 教学模型','binding':'custom',
        'api_format':'openai_chat_completions','base_url':base,'api_key':key,
        'models':[{'id':'mindtrace-teaching-model','name':model,'model':model}]}
    existing=catalog['services'].get('llm',{})
    profiles=[p for p in existing.get('profiles',[]) if p.get('id')!=profile['id']]
    catalog['services']['llm']={**existing,'active_profile_id':profile['id'],
        'active_model_id':'mindtrace-teaching-model','profiles':profiles+[profile]}
    service.save(catalog)
    return True


async def open_lesson(store,binding,submission_id,*,mode='tutor'):
    """Opening a source creates native records, never makes a model request."""
    from deeptutor.app import DeepTutorApp
    from deeptutor.services.session import get_session_store
    from deeptutor.learning.models import LearningModule,KnowledgePoint,KnowledgeType,TopicSource,TopicSourceKind,TopicMetadata
    from deeptutor.learning.service import LearningService
    from deeptutor.learning.storage import LearningStore
    from deeptutor.services.memory.store import get_memory_store
    from deeptutor.services.memory.trace import TraceEvent
    content=source(binding,submission_id)
    revision=content['source_revision']
    prior=store.lesson(binding['id'],submission_id,revision)
    if prior:
        with user_scope(binding):
            DeepTutorApp().update_record(prior['notebook_id'],prior['record_id'],output=context_text(content))
            native_learning=LearningStore()
            topic=native_learning.get_topic(prior['path_id'])
            if topic and not topic.metadata.goal:
                native_learning.put_topic(TopicMetadata(path_id=prior['path_id'],goal='理解本题关键步骤并独立订正。'),topic.sources)
            native_learning.bind_session(prior['path_id'],prior['session_id'])
        return prior
    with user_scope(binding):
        app=DeepTutorApp()
        for old in store.lessons_for(binding['id'],submission_id):
            if old['revision']==revision:continue
            app.update_record(old['notebook_id'],old['record_id'],
                title='【历史依据，已更新】'+content['question'][:70],
                summary='此记录的教师依据已失效，必须读取当前mindtrace_source后再教学。',
                metadata={'mindtrace_superseded':True,'current_source_revision':revision})
        native=get_session_store()
        session=await native.create_session(title='循理 · '+(content['question_no'] or content['topic']))
        notebook=next((r for r in app.list_notebooks() if r['name']=='MindTrace 原题与教师反馈'),None)
        if notebook is None:notebook=app.create_notebook('MindTrace 原题与教师反馈','来自课堂的版本化原始证据；不是掌握程度。')
        added=app.add_record(notebook_ids=[notebook['id']],record_type='chat',
            title=content['question'][:100],user_query='原题、原始作答和批改依据',output=context_text(content),
            metadata={'mindtrace_submission_id':submission_id,'source_revision':revision})
        record=added['record']
        path_id='mt-'+__import__('hashlib').sha256((binding['id']+submission_id+revision).encode()).hexdigest()[:24]
        points=content['knowledge_points'][:4] or [content['topic']+'：理解本题条件与关键步骤']
        module=LearningModule(id='original-problem',name='本题理解与独立订正',order=0,
            knowledge_points=[KnowledgePoint(id='objective-'+str(i),name=point,type=KnowledgeType.PROCEDURE,
                                             module_id='original-problem') for i,point in enumerate(points)])
        native_learning=LearningStore()
        LearningService(native_learning).create_topic(path_id,modules=[module],name=content['question'][:80],
            metadata=TopicMetadata(path_id=path_id,goal='理解本题关键步骤并独立订正。'),
            sources=[TopicSource(id='teacher-source',kind=TopicSourceKind.NOTEBOOK,
                source_id=notebook['id'],label='本题原始作答与教师反馈',excerpt=context_text(content)[:12000],
                metadata={'record_id':record['id'],'source_revision':revision})])
        native_learning.bind_session(path_id,session['id'])
        await native.update_session_preferences(session['id'],{
            'language':'zh','capability':'mastery_path' if mode=='tutor' else 'deep_solve',
            'workspace_mode':'mastery' if mode=='tutor' else '',
            'mastery_path_id':path_id if mode=='tutor' else None,'mastery_session_mode':'study',
            'notebook_references':[{'notebook_id':notebook['id'],'record_ids':[record['id']]}]})
        # Native visible source notice; no fabricated student message or answer.
        await native.add_message(session['id'],'assistant',
            '已关联你的原题、作答与批改反馈。请在下方提出疑问，或说明希望从哪一步开始。',
            capability='chat',metadata={'mindtrace_source_notice':True})
        await get_memory_store().emit(TraceEvent.new('notebook','mindtrace_source_linked',
            {'notebook_id':notebook['id'],'record_id':record['id'],'source_revision':revision,
             'status':'source_available_not_mastery'},session_id=session['id']))
    result=dict(principal_id=binding['id'],submission_id=submission_id,revision=revision,
                session_id=session['id'],notebook_id=notebook['id'],record_id=record['id'],path_id=path_id)
    store.put_lesson(result)
    return store.lesson(binding['id'],submission_id,revision)


def configure_home(home):
    """Enable official auth before importing its API module (fail closed)."""
    home=Path(home).resolve();settings=home/'data'/'user'/'settings';settings.mkdir(parents=True,exist_ok=True)
    path=settings/'auth.json'
    value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    value.update(enabled=True,token_expire_hours=24,cookie_secure=os.getenv('MINDTRACE_TUTOR_SECURE_COOKIE')=='1')
    path.write_text(json.dumps(value),encoding='utf-8')
    system=settings/'system.json'
    config=json.loads(system.read_text(encoding='utf-8')) if system.exists() else {}
    origins=set(config.get('cors_origins',[]))
    origins.update(('http://127.0.0.1:8592','http://localhost:8592'))
    config['cors_origins']=sorted(origins)
    system.write_text(json.dumps(config),encoding='utf-8')
    os.environ['DEEPTUTOR_HOME']=str(home)


async def record_learning_event(binding,kind,payload):
    """Use upstream durable source traces; do not fabricate a mastery score."""
    from deeptutor.services.memory.store import get_memory_store
    from deeptutor.services.memory.trace import TraceEvent
    with user_scope(binding):
        await get_memory_store().emit(TraceEvent.new('notebook',kind,
            {**payload,'authority':'mindtrace_classroom','instruction':'来源记录可能被教师更新；判断当前学习状态必须重新读取mindtrace_learning_evidence。'}))
