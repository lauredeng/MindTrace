"""Server-side HTTPS adapter. Bearer classroom codes never enter URLs."""
import os
from urllib.parse import urlparse
import httpx


def enabled():return bool(os.getenv('MINDTRACE_BACKEND_URL','').strip()) and os.getenv('MINDTRACE_HEADLESS')!='1'


def request(method,path,*,code=None,data=None,content=None,binary=False):
    base=os.environ['MINDTRACE_BACKEND_URL'].rstrip('/')
    parsed=urlparse(base)
    if (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1'))
        or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise RuntimeError('后端连接配置无效，请联系管理员。')
    headers={'Authorization':'Bearer '+code} if code else {}
    if content is not None:headers['Content-Type']='application/octet-stream'
    try:
        with httpx.Client(timeout=30,follow_redirects=False,trust_env=parsed.hostname not in ('localhost','127.0.0.1')) as client:
            response=client.request(method,base+path,headers=headers,json=data,content=content)
    except httpx.HTTPError:raise RuntimeError('学习服务暂时无法连接，已有数据仍保留在服务端。') from None
    if response.status_code>=300:
        if response.status_code in (401,403):raise ValueError('课堂连接无效或没有操作权限。')
        if response.status_code==409:raise ValueError('记录已更新，请刷新课堂后重试。')
        if response.status_code==404:return None
        raise RuntimeError('服务端未完成本次操作，请检查输入或稍后重试。')
    return response.content if binary else response.json()
