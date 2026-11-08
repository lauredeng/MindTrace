"""Offline SDK runtime tests; no credentials or external API are used."""
import httpx
import pytest
from dataclasses import replace
from openai import OpenAI as RealOpenAI
from core import ai
from core.limits import Limits,UsageLimitError
from core.usage import for_session

def config():
    return {'key':'SYNTHETIC-RUNTIME-CREDENTIAL','base_url':'https://api.deepseek.com','model':'runtime-model',
            'vision_model':'runtime-model','timeout':'30','retries':'1','input_price':'1','output_price':'2','currency':'CNY'}

def success():
    return {'id':'fixture','object':'chat.completion','created':0,'model':'runtime-model',
            'choices':[{'index':0,'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}

def transport(monkeypatch,responder):
    monkeypatch.setattr(ai,'config',config)
    monkeypatch.setattr(ai.time,'sleep',lambda n:None)
    monkeypatch.setattr(ai,'OpenAI',lambda **kw:RealOpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(responder))))

def test_retry_is_separately_admitted_and_usage_is_actual(monkeypatch):
    sent=[]
    def respond(req):
        sent.append(1)
        return httpx.Response(500,json={'error':{'message':'raw upstream fixture'}}) if len(sent)==1 else httpx.Response(200,json=success())
    transport(monkeypatch,respond)
    session='test-runtime-retry'
    assert ai.completion([{'role':'user','content':'fixture'}],session_id=session)=='ok'
    events=for_session(session)
    assert [x['status'] for x in events]==['http_500','completed']
    assert events[0]['prompt_tokens'] is None
    assert events[1]['prompt_tokens']==10 and events[1]['estimated_cost']==0.00002
    assert 'SYNTHETIC-RUNTIME-CREDENTIAL' not in str(events)
    assert ai.LIMITER.day_count==2

def test_retry_cannot_escape_daily_limit(monkeypatch):
    sent=[]
    def respond(req):
        sent.append(1)
        return httpx.Response(500,json={'error':{'message':'fixture'}})
    transport(monkeypatch,respond)
    monkeypatch.setattr(ai.Limits,'configured',lambda:replace(Limits(),global_day=1))
    with pytest.raises(UsageLimitError):
        ai.completion([{'role':'user','content':'fixture'}],session_id='test-runtime-block')
    assert len(sent)==1
    assert for_session('test-runtime-block')[-1]['status']=='blocked'


@pytest.mark.parametrize(('content','valid'),[('```json\n{"records":[]}\n```',True),('{"records":[}',False)])
def test_ocr_json_accepts_exact_code_fence_and_labels_malformed_payload(monkeypatch,content,valid):
    payload=success()
    payload['choices'][0]['message']['content']=content
    transport(monkeypatch,lambda _:httpx.Response(200,json=payload))
    def recognize():
        return ai.completion([{'role':'user','content':'fixture'}],vision=True,json_output=True,
                             purpose='ocr',session_id='runtime-ocr-json')
    if valid:
        assert recognize()=={'records':[]}
    else:
        with pytest.raises(ai.InvalidModelJSON):
            recognize()
        assert for_session('runtime-ocr-json')[-1]['status']=='invalid_json'

@pytest.mark.parametrize('field,value',[('timeout','2'),('timeout','999'),('retries','3'),('retries','-1')])
def test_invalid_runtime_config_rejected(monkeypatch,field,value):
    cfg=config();cfg[field]=value
    monkeypatch.setattr(ai,'config',lambda:cfg)
    with pytest.raises(RuntimeError,match='配置无效'):
        ai.completion([{'role':'user','content':'fixture'}])

