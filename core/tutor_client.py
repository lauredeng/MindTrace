"""Server-side handoff to the official DeepTutor service, without codes in URLs."""
import os
from urllib.parse import urlparse
import httpx


def configured():return bool(os.getenv('MINDTRACE_TUTOR_URL','').strip())


def launch(code,submission_id=None):
    base=os.getenv('MINDTRACE_TUTOR_URL','').rstrip('/')
    parsed=urlparse(base)
    if (parsed.scheme!='https' and not(parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost'))
        or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('辅导服务地址尚未正确配置。')
    try:
        with httpx.Client(timeout=15,follow_redirects=False,trust_env=parsed.hostname not in ('127.0.0.1','localhost')) as client:
            response=client.post(base+'/api/mindtrace/tickets',headers={'Authorization':'Bearer '+code},
                                 json={'submission_id':submission_id})
        if response.status_code!=200:raise ValueError('辅导入口暂时不可用，请刷新课堂后再试。')
        result=response.json()
        token=result['ticket']
        if not isinstance(token,str) or not token or len(token)>100 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in token):
            raise ValueError('辅导入口响应无效。')
        public=os.getenv('MINDTRACE_TUTOR_WEB_URL','').rstrip('/') or base
        target=urlparse(public)
        if (not target.hostname or target.username or target.password or target.query or target.fragment
            or target.scheme!='https' and not(target.scheme=='http' and target.hostname in ('127.0.0.1','localhost'))):
            raise ValueError('学习界面地址配置无效。')
        return public+'/mindtrace#ticket='+token
    except (httpx.HTTPError,KeyError,TypeError):
        raise RuntimeError('辅导服务暂时无法连接；原有作业与错题仍已保存。') from None
