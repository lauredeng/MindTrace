"""UI-independent bounded worker. Start explicitly; no model calls on import."""
from copy import deepcopy
import json
import os
import time
from threading import Event,Thread
from sqlite3 import Error as SQLiteError
from uuid import uuid4

from core import ai, product as p
from core.limits import Limits, request_units
from core.repository import Repository


def configured_repository():
    path=os.getenv('MINDTRACE_DATABASE','').strip()
    return Repository(path) if path else None


class Worker:
    def __init__(self,repository,call=None,*,owner=None):
        self.repository=repository
        self.owner=owner or str(uuid4())
        self.call=call

    def _call(self,job,*args,**kwargs):
        if not self.repository.renew(job):raise RuntimeError('任务已被取消或接管，未发起后续请求。')
        system,user=args
        units=request_units([{'role':'system','content':system},{'role':'user','content':user}],
                            kwargs.get('max_tokens',1800),output_limit=9500)
        limits=Limits.configured()
        reservation=self.repository.admit(job['id'],units,minute=limits.global_minute,
                                          daily=limits.global_day,daily_units=limits.daily_units,concurrent=limits.concurrent)
        try:
            if self.call is not None:result=self.call(system,user,**kwargs)
            else:
                result=ai.completion([{'role':'system','content':system},{'role':'user','content':user}],
                                     session_id='job-'+job['id'],**kwargs)
        except BaseException:
            # Timeout may have incurred provider cost. Never label it zero usage.
            self.repository.settle(reservation,'unknown_or_failed')
            raise
        finally:
            from core.usage import for_session
            self.repository.append_usage(job['workspace_id'],for_session('job-'+job['id']))
        self.repository.settle(reservation,'completed')
        return result

    def tick(self):
        job=self.repository.claim(self.owner)
        if job is None:return False
        stop=Event()
        def heartbeat():
            while not stop.wait(20):
                try:
                    if not self.repository.renew(job):return
                except (ValueError,OSError,SQLiteError):return
        thread=Thread(target=heartbeat,daemon=True);thread.start()
        try:return self._execute_job(job)
        finally:stop.set();thread.join(timeout=2)

    def _execute_job(self,job):
        workspace=self.repository.load(workspace_id=job['workspace_id'])
        sub=next((s for s in workspace['submissions'] if s['id']==job['submission_id']),None)
        payload=json.loads(job['payload'])
        if sub is None:
            self.repository.defer(job,reason='原始作答不存在，任务已停止。',terminal=True);return True
        if sub['fingerprint']!=payload['fingerprint'] or sub.get('reference_revision')!=payload['reference_revision'] or sub.get('grading_revision')!=payload.get('grading_revision') or p.effective(workspace,sub)['confirmed']:
            self.repository.finish(job,{'id':str(uuid4())});return True
        if job['stage']=='deep' and (p.latest(sub,'quick_checks') or {}).get('id')!=payload.get('quick_id'):
            self.repository.finish(job,{'id':str(uuid4())});return True
        material=deepcopy(sub)
        batch=next(b for b in workspace['batches'] if b['id']==job['batch_id'])
        reference=next((entry['confirmed'] for entry in batch.get('answer_keys',{}).values()
                        if entry.get('confirmed',{}).get('id')==sub.get('reference_revision')),None)
        def call(*args,**kwargs):return self._call(job,*args,**kwargs)
        try:
            if job['stage']=='quick':result=p.quick_check(material,call,reference=reference)
            else:result=p.deep_analyze(material,call,teacher_only=material.get('grading_policy')==p.CLASSROOM_POLICY,reference=reference)
            if result['status']=='completed':self.repository.finish(job,result)
            elif result.get('error_type')=='UsageLimitError':
                reason=result.get('limit_reason')
                delay=result.get('retry_after') if reason in ('minute','busy','provider') else None
                self.repository.defer(job,reason=result['error'],delay=delay)
            elif result.get('error_type')=='ServiceUnavailable' and job['attempts']<3:
                self.repository.defer(job,reason=result['error'],delay=2**job['attempts'])
            else:self.repository.defer(job,reason=result.get('error','任务未完成，请检查材料。'),terminal=True)
        except (ValueError,RuntimeError,OSError):
            self.repository.defer(job,reason='后台处理未完成，请查看服务日志并检查配置。',terminal=job['attempts']>=3,
                                  delay=2**job['attempts'] if job['attempts']<3 else None)
        return True

    def run(self,stop=None):
        while stop is None or not stop.is_set():
            busy=self.tick()
            if not busy:
                if stop is None:time.sleep(1)
                else:stop.wait(1)
