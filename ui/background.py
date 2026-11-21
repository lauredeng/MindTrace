"""Persisted task status. Fragment refreshes display; it never runs model work."""
import os
import streamlit as st
from core.background import configured_repository

LABEL={'queued':'排队中','running':'处理中','retry_wait':'等待自动重试','blocked':'需要处理额度或配置',
       'failed':'需检查后重试','completed':'已保存','cancelled':'已取消','stale':'原答或判定已更新'}


def enabled(rt):
    from core import backend_client
    return (bool(rt.access) and backend_client.enabled() or os.getenv('MINDTRACE_BACKGROUND')=='1' and bool(os.getenv('MINDTRACE_DATABASE'))) and not rt.shared and rt.key is None


def enqueue(rt,batch_id):
    from core import backend_client
    if rt.access and backend_client.enabled():return backend_client.request('POST','/assignments/'+batch_id+'/grade',code=rt.access['code'])
    return configured_repository().enqueue_batch(rt.w['id'],batch_id,retry_failed=True)


def grading_ready(rt):
    from core import backend_client
    if rt.access and backend_client.enabled():
        try:return bool(backend_client.request('GET','/health').get('model_configured'))
        except (ValueError,RuntimeError):return False
    return rt.ready()


@st.fragment(run_every=2.0)
def task_panel(rt,batch_id):
    from core import backend_client
    remote=bool(rt.access) and backend_client.enabled()
    repo=None if remote else configured_repository()
    jobs=backend_client.request('GET','/assignments/'+batch_id+'/jobs',code=rt.access['code']) if remote else repo.jobs(rt.w['id'],batch_id)
    if not jobs:return
    before=rt.w['storage_version']
    rt.prepare_workspace()
    if rt.w['storage_version']!=before:st.rerun(scope='app')
    finished=sum(j['status'] in ('completed','stale') for j in jobs)
    active=any(j['status'] in ('queued','running','retry_wait') for j in jobs)
    with st.container(border=True):
        st.markdown('**后台处理进度**')
        st.progress(finished/max(1,len(jobs)),text=f'已保存 {finished}/{len(jobs)} 个处理步骤')
        if active:
            available=backend_client.request('GET','/health')['worker_available'] if remote else repo.worker_available()
            if available:st.caption('任务已交给后台处理。可以离开此页面，返回后查看结果。')
            else:st.warning('后台服务尚未连接，任务已保存。请联系管理员启动处理服务。')
        statuses={LABEL[j['status']]:sum(x['status']==j['status'] for x in jobs) for j in jobs}
        st.caption(' · '.join(f'{name} {count}' for name,count in statuses.items()))
        errors=list(dict.fromkeys(j['error'] for j in jobs if j.get('error') and j['status'] in ('failed','blocked','retry_wait')))
        for error in errors[:3]:st.info(error)
        if active and st.button('停止后续批改',key='cancel_jobs_'+batch_id):
            if remote:backend_client.request('POST','/assignments/'+batch_id+'/cancel',code=rt.access['code'])
            else:repo.cancel_batch(rt.w['id'],batch_id)
            st.rerun(scope='app')
        if any(j['status'] in ('failed','blocked','cancelled') for j in jobs) and st.button('重试未完成任务',key='retry_jobs_'+batch_id):
            enqueue(rt,batch_id);st.rerun(scope='app')
