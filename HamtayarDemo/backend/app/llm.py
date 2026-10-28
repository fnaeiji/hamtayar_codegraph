"""OpenAI-compatible model requests with credential-free diagnostics."""
import json
from urllib.parse import urlsplit,urlunsplit
import httpx
from .config import setting

class ModelError(Exception):
    def __init__(self,code,message,status=None):
        self.diagnostic={'code':code,'message':message}
        if status is not None:self.diagnostic['http_status']=status
        super().__init__(message)

def configuration():
    model=setting('LLM_MODEL').strip()
    if not model:raise ModelError('LLM_NOT_CONFIGURED','Set LLM_MODEL and LLM_BASE_URL in Settings. API key is required only if your provider requires authentication.')
    raw=setting('LLM_BASE_URL','https://api.openai.com/v1').strip().rstrip('/')
    try:
        parsed=urlsplit(raw)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError()
        style=setting('LLM_API_STYLE','chat_completions')
        if style not in ('chat_completions','responses'):raise ValueError()
        auth=setting('LLM_AUTH_MODE','bearer')
        if auth not in ('bearer','api-key','none'):raise ValueError()
        timeout=int(setting('LLM_TIMEOUT_SECONDS','90'))
        token_parameter=setting('LLM_TOKEN_PARAMETER','max_tokens')
        if token_parameter not in ('max_tokens','max_completion_tokens'):raise ValueError()
        if not 5<=timeout<=600:raise ValueError()
    except ValueError:raise ModelError('LLM_INVALID_CONFIGURATION','Use an http(s) base URL without credentials/query; API style chat_completions or responses; timeout 5..600 seconds.') from None
    # Accept a base URL or the complete endpoint, without double-appending it.
    endpoint='responses' if style=='responses' else 'chat/completions'
    for suffix in ('/chat/completions','/responses'):
        if parsed.path.endswith(suffix):parsed=parsed._replace(path=parsed.path[:-len(suffix)]);break
    url=urlunsplit(parsed).rstrip('/')+'/'+endpoint
    return {'model':model,'url':url,'style':style,'timeout':timeout,'token_parameter':token_parameter,'auth':auth}

async def request(messages, max_tokens=1200):
    config=configuration();headers={}
    key=setting('LLM_API_KEY').strip()
    if key.lower().startswith('bearer '):key=key[7:].strip()
    if config['auth']!='none' and any(ord(c)<33 or ord(c)>126 for c in key):
        raise ModelError('LLM_INVALID_KEY','API key contains whitespace or unsupported characters. Paste only the provider API key.')
    if config['auth']=='bearer' and key:headers['Authorization']='Bearer '+key
    elif config['auth']=='api-key' and key:headers['api-key']=key
    if config['style']=='responses':
        payload={'model':config['model'],'input':messages,'max_output_tokens':max_tokens}
    else:
        payload={'model':config['model'],'messages':messages,config['token_parameter']:max_tokens}
    try:
        async with httpx.AsyncClient(timeout=config['timeout']) as client:
            response=await client.post(config['url'],headers=headers,json=payload)
    except httpx.TimeoutException:
        raise ModelError('LLM_TIMEOUT','Model request timed out. Check model/server load or increase LLM_TIMEOUT_SECONDS.') from None
    except httpx.ConnectError:
        raise ModelError('LLM_CONNECTION_FAILED','Cannot reach model server. Check LLM_BASE_URL, server availability, DNS, proxy and TLS certificate.') from None
    except httpx.HTTPError:
        raise ModelError('LLM_TRANSPORT_ERROR','Model transport failed. Check local network/proxy and server logs.') from None
    if response.is_error:
        status=response.status_code
        messages={401:'Authentication rejected (HTTP 401). Check the API key belongs to this endpoint and the selected authentication mode. Save and test again; a chat subscription is not an API credential.',403:'Provider denied access: check key permissions, model access and provider restrictions.',404:'Endpoint or model not found: check LLM_BASE_URL, LLM_MODEL and API style.',429:'Rate limit or quota exceeded: check provider quota and retry later.',400:'Provider rejected the request: check model/API compatibility, context length and token limit.',422:'Provider rejected the payload: check API style, model and token limit.'}
        raise ModelError('LLM_HTTP_'+str(status),messages.get(status,'Model server returned an error; inspect provider server logs.'),status)
    try:
        result=response.json()
        if config['style']=='responses':
            answer='\n'.join(block['text'] for item in result.get('output',[]) if item.get('type')=='message' for block in item.get('content',[]) if block.get('type')=='output_text')
        else:
            answer=result['choices'][0]['message']['content']
            if isinstance(answer,list):answer='\n'.join(x.get('text','') for x in answer if x.get('type')=='text')
        if not isinstance(answer,str) or not answer.strip():raise ValueError()
        return answer
    except (ValueError,KeyError,TypeError,IndexError,AttributeError):
        raise ModelError('LLM_INVALID_RESPONSE','Server response did not contain assistant text. Check API style; the model may have returned only reasoning, a refusal or an incomplete response.') from None

async def connection_test():
    details={}
    try:
        cfg=configuration()
        details={'endpoint':cfg['url'],'model':cfg['model'],'api_style':cfg['style'],'auth_mode':cfg['auth'],'key_present':bool(setting('LLM_API_KEY').strip()),'key_sent':cfg['auth']!='none' and bool(setting('LLM_API_KEY').strip())}
        await request([{'role':'user','content':'Reply with OK.'}],max_tokens=64)
        return {'ok':True,**details,'message':'Model request succeeded. No repository content was sent.'}
    except ModelError as exc:return {'ok':False,**details,**exc.diagnostic}
