import asyncio
import httpx
import pytest
from app import config,llm

@pytest.fixture
def model(monkeypatch):
    monkeypatch.setitem(config.values,'LLM_MODEL','local-model')
    monkeypatch.setitem(config.values,'LLM_BASE_URL','http://localhost:11434/v1')
    monkeypatch.setitem(config.values,'LLM_API_KEY','')
    monkeypatch.setitem(config.values,'LLM_API_STYLE','chat_completions')
    return monkeypatch

def client(monkeypatch,handler):
    real=httpx.AsyncClient
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))

def test_local_no_key_and_endpoint_normalization(model):
    model.setitem(config.values,'LLM_BASE_URL','http://localhost:11434/v1/chat/completions')
    def handle(request):
        assert request.url.path=='/v1/chat/completions' and 'authorization' not in request.headers
        return httpx.Response(200,json={'choices':[{'message':{'content':'OK'}}]})
    client(model,handle)
    assert asyncio.run(llm.connection_test())['ok']

@pytest.mark.parametrize('status',[400,401,403,404,422,429,500])
def test_http_errors_are_actionable_and_never_echo_provider_body(model,status):
    model.setitem(config.values,'LLM_API_KEY','private-key')
    client(model,lambda request:httpx.Response(status,json={'error':{'message':'private-key source code secret'}}))
    result=asyncio.run(llm.connection_test())
    assert result['http_status']==status and result['code']=='LLM_HTTP_'+str(status)
    assert 'private-key' not in str(result) and 'source code' not in str(result)

@pytest.mark.parametrize('exception,code',[(httpx.ConnectError('secret'),'LLM_CONNECTION_FAILED'),(httpx.ReadTimeout('secret'),'LLM_TIMEOUT')])
def test_network_diagnostics(model,exception,code):
    def fail(request):raise exception
    client(model,fail)
    assert asyncio.run(llm.connection_test())['code']==code

@pytest.mark.parametrize('body',[{},[],{'choices':[]},{'choices':[{'message':{'content':None}}]}])
def test_invalid_json_shapes_preserve_diagnostics(model,body):
    client(model,lambda request:httpx.Response(200,json=body))
    assert asyncio.run(llm.connection_test())['code']=='LLM_INVALID_RESPONSE'

def test_responses_style_and_token_parameter(model):
    model.setitem(config.values,'LLM_API_STYLE','responses')
    def handle(request):
        assert request.url.path=='/v1/responses'
        return httpx.Response(200,json={'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]})
    client(model,handle)
    assert asyncio.run(llm.connection_test())['ok']


def test_chat_failure_preserves_context_and_diagnostic(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as api
    pack={'evidence':[{'id':'E1','text':'private source'}]}
    monkeypatch.setattr(api,'context',lambda *args:pack)
    async def fail(*args,**kwargs):raise llm.ModelError('LLM_HTTP_401','Authentication failed.',401)
    monkeypatch.setattr(llm,'request',fail)
    with TestClient(api.app) as client:
        response=client.post('/api/projects/p/chat',json={'question':'test'})
    assert response.status_code==200 and response.json()['context']==pack
    assert response.json()['diagnostic']['http_status']==401


def test_chat_max_completion_tokens(model):
    import json
    model.setitem(config.values,'LLM_TOKEN_PARAMETER','max_completion_tokens')
    def handle(request):
        body=json.loads(request.content)
        assert 'max_completion_tokens' in body and 'max_tokens' not in body
        return httpx.Response(200,json={'choices':[{'message':{'content':'OK'}}]})
    client(model,handle)
    assert asyncio.run(llm.connection_test())['ok']
