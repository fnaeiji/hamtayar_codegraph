import io
import os
import tempfile
import zipfile
from pathlib import Path
os.environ['HAMTAYAR_RUNTIME']=tempfile.mkdtemp(prefix='hamtayar-test-')
from fastapi.testclient import TestClient
from app.main import app
from app import archive,store,graph

def zip_bytes(entries):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        for name,value in entries.items():z.writestr(name,value)
    return stream.getvalue()

def test_zip_to_source_and_scope():
    with TestClient(app) as c:
        p=c.post('/api/projects',files={'file':('a.zip',zip_bytes({'src/a.py':'def same():\n    return 1\n'}))}).json()
        q=c.post('/api/projects',files={'file':('b.zip',zip_bytes({'src/b.py':'def same():\n    return 2\n'}))}).json()
        assert p['id']!=q['id']
        assert c.get(f"/api/projects/{p['id']}/source",params={'path':'src/a.py'}).json()['text'].endswith('return 1\n')
        assert c.get(f"/api/projects/{p['id']}/source",params={'path':'src/b.py'}).status_code==400
        assert c.get(f"/api/projects/{p['id']}/source",params={'path':'../../metadata.sqlite3'}).status_code==400
        assert c.get(f"/api/projects/{p['id']}/graph").status_code==400

def test_unsafe_archives():
    with TestClient(app) as c:
        for name in ['../escape.py','C:/escape.py','/absolute.py','a/CON.txt','a/../escape.py']:
            assert c.post('/api/projects',files={'file':('x.zip',zip_bytes({name:'bad'}))}).status_code==400
        assert c.post('/api/projects',files={'file':('bad.zip',b'bad')}).status_code==400
        assert c.post('/api/projects',files={'file':('x.zip',zip_bytes({'A.py':'a','a.py':'b'}))}).status_code==400

def test_origin_guard():
    with TestClient(app) as c:
        assert c.post('/api/connection/test',headers={'origin':'https://evil.example'}).status_code==403

def test_no_arbitrary_cypher():
    p={'id':'query-test','status':'ready','active_index':'owned'};store.save(p)
    with TestClient(app) as c:
        assert c.post('/api/projects/query-test/query',json={'template':'MATCH (n) DETACH DELETE n'}).status_code==400

def test_failed_generation_keeps_previous(monkeypatch):
    from app.jobs import Jobs
    import threading
    p={'id':'failed-test','status':'queued','active_index':'previous','logs':[]};store.save(p)
    def fail(*args,**kwargs):raise RuntimeError('unavailable')
    monkeypatch.setattr(graph,'query',fail)
    jobs=Jobs();jobs.run(p['id'],'new',threading.Event());jobs.pool.shutdown()
    assert store.get(p['id'])['status']=='failed'
    assert store.get(p['id'])['active_index']=='previous'

def test_recovery_preserves_index():
    from app.jobs import Jobs
    store.save({'id':'interrupted','status':'indexing','active_index':'old'})
    jobs=Jobs();jobs.recover();jobs.pool.shutdown()
    assert store.get('interrupted')['status']=='interrupted'
    assert store.get('interrupted')['active_index']=='old'

def test_graph_queries_scope_both_endpoints(monkeypatch):
    calls=[]
    def capture(q,**params):
        calls.append((q,params))
        return [{'node':{'id':'my-symbol'}}] if ' AS node' in q else []
    monkeypatch.setattr(graph,'query',capture)
    graph.neighborhood('my-index',symbol='my-symbol')
    assert 'a.index=$index AND b.index=$index' in calls[1][0]
    assert calls[1][1]['index']=='my-index'

def test_publish_scopes_identity_and_preserves_legacy(publication_db,tmp_path):
    graph.publish('A','v1',tmp_path);graph.publish('B','v2',tmp_path)
    assert set(publication_db.written['v1']).isdisjoint(publication_db.written['v2'])
    assert all('DELETE' not in q for q,p in publication_db.calls)

def test_settings_do_not_return_secrets(monkeypatch,tmp_path):
    from app import config
    monkeypatch.setattr(config,'ROOT',tmp_path)
    with TestClient(app) as c:
        r=c.post('/api/settings',json={'values':{'LLM_API_KEY':'test-provider-secret'}})
        assert r.status_code==200
        assert 'test-provider-secret' not in r.text
        assert r.json()['secrets_present']['LLM_API_KEY']
        assert c.post('/api/settings',json={'values':{'ARBITRARY':'bad'}}).status_code==400
    config.values.pop('LLM_API_KEY',None)

def test_binary_and_dependencies_excluded(tmp_path):
    path=tmp_path/'archive.zip';path.write_bytes(zip_bytes({'a.py':'def x(): pass','node_modules/a.js':'ignored','a.bin':b'\x00abc'}))
    files=archive.unpack(path,tmp_path/'extracted')
    assert sum(not f['excluded'] for f in files)==1

def test_graph_publish_requires_declarations(publication_db,tmp_path):
    import pytest
    publication_db.declarations=0
    with pytest.raises(ValueError,match='no usable code declarations'):graph.publish('project','attempt',tmp_path)

def test_context_without_llm(monkeypatch):
    with TestClient(app) as c:
        p=c.post('/api/projects',files={'file':('context.zip',zip_bytes({'a.py':'def sample():\n    return 42\n'}))}).json()
        store.update(p['id'],active_index='context-index',status='ready')
        monkeypatch.setattr(graph,'search',lambda *a,**k:[{'node':{'id':'one','name':'sample','path':'a.py','line':1,'end':2}}])
        monkeypatch.setattr(graph,'neighborhood',lambda *a,**k:{'nodes':[],'edges':[]})
        result=c.post(f"/api/projects/{p['id']}/context",json={'question':'sample'}).json()
        assert result['evidence'][0]['text']=='def sample():\n    return 42'
        assert result['evidence'][0]['id']=='E1'
        assert result['source_version']==p['source_version']
