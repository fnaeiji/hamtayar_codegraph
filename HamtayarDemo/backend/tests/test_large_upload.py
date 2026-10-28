import asyncio
import io
import zipfile
from threading import Event
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app import archive, store, uploads
from app.jobs import Jobs
from app.main import app

def payload(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,data in files.items():z.writestr(name,data)
    return out.getvalue()

def test_upload_returns_202_before_extraction(monkeypatch):
    from app.main import jobs
    queued=Mock();monkeypatch.setattr(jobs,'extract',queued)
    with TestClient(app) as client:
        result=client.post('/api/projects/upload?filename=project.zip',content=payload({'a.py':'def f(): pass'}))
        assert result.status_code==202,result.text
        project=result.json()
        assert project['status']=='archive_queued'
        assert project['files']==[]
        queued.assert_called_once_with(project['id'])
        assert (uploads.RUNTIME/'workspaces'/project['id']/'upload.archive').is_file()
        assert not (uploads.RUNTIME/'workspaces'/project['id']/'source').exists()
        worker=Jobs();worker.extract_archive(project['id'],Event());worker.pool.shutdown()
        assert store.get(project['id'])['status']=='ready_to_index'

def test_stream_413_before_queue(monkeypatch):
    monkeypatch.setattr(uploads,'MAX_UPLOAD',8)
    with TestClient(app) as client:
        response=client.post('/api/projects/upload?filename=project.zip',content=b'0123456789')
        assert response.status_code==413
        assert 'upload limit' in response.json()['detail']

def test_stream_limit_without_content_length(monkeypatch):
    monkeypatch.setattr(uploads,'MAX_UPLOAD',8)
    class Request:
        headers={}
        async def stream(self):
            yield b'12345'
            yield b'67890'
    before=set((uploads.RUNTIME/'workspaces').glob('*'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads.receive(Request(),'big.rar'))
    assert exc.value.status_code==413
    assert set((uploads.RUNTIME/'workspaces').glob('*'))==before

def test_background_extraction_failure_persisted(monkeypatch):
    from app.main import jobs
    monkeypatch.setattr(jobs,'extract',Mock())
    with TestClient(app) as client:
        result=client.post('/api/projects/upload?filename=broken.rar',content=b'bad archive').json()
    worker=Jobs();worker.extract_archive(result['id'],Event());worker.pool.shutdown()
    assert store.get(result['id'])['status']=='extraction_failed'
    assert not (uploads.RUNTIME/'workspaces'/result['id']/'source').exists()

def test_manifest_pagination_and_bounded_polling():
    files=[{'path':f'src/{i}.py','excluded':False} for i in range(1200)]
    store.save({'id':'large-manifest','status':'ready_to_index','files':files,'logs':['log']*500,'active_index':None})
    with TestClient(app) as c:
        result=c.get('/api/projects/large-manifest').json()
        assert len(result['files'])==500
        assert result['files_total']==1200
        assert len(result['logs'])==200
        page=c.get('/api/projects/large-manifest/files?offset=1000&limit=200').json()
        assert page['total']==1200
        assert page['files'][0]['path']=='src/1000.py'
        assert c.get('/api/projects/large-manifest/files?offset=-1').status_code==400

def test_extraction_can_cancel(tmp_path):
    data=tmp_path/'source.zip';data.write_bytes(payload({'a.py':'def f(): pass'}))
    event=Event();event.set()
    with pytest.raises(ValueError,match='Cancelled'):
        archive.unpack(data,tmp_path/'source',event)

def test_index_blocked_during_extraction():
    worker=Jobs()
    store.save({'id':'extracting-test','status':'extracting','files':[]})
    with pytest.raises(ValueError):worker.submit('extracting-test')
    worker.pool.shutdown()

def test_exclusions_do_not_consume_extraction_budget(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(archive,'MAX_EXPANDED',20)
    monkeypatch.setattr(archive,'MAX_FILE',15)
    def item(name,size):return SimpleNamespace(filename=name,file_size=size,is_dir=lambda:False)
    entries=[item('NODE_MODULES/a.js',10000),item('obj/main.dll',10000),item('huge.py',10000),item('a.py',13)]
    opener=Mock(side_effect=lambda e:io.BytesIO(b'def f(): pass'))
    files=archive._consume(entries,opener,tmp_path)
    assert len(files)==4
    assert sum(f['excluded'] for f in files)==3
    opener.assert_called_once_with(entries[-1])
    assert (tmp_path/'a.py').read_text()=='def f(): pass'

def test_selected_budget_error_names_file_and_setting(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(archive,'MAX_EXPANDED',10)
    entries=[SimpleNamespace(filename='a.py',file_size=11,is_dir=lambda:False)]
    opener=Mock()
    with pytest.raises(ValueError,match='MAX_EXPANDED_MB at a.py'):
        archive._consume(entries,opener,tmp_path)
    opener.assert_not_called()

def test_retry_extraction_reuses_uploaded_archive(monkeypatch):
    from app.main import jobs
    monkeypatch.setattr(jobs,'extract',Mock())
    with TestClient(app) as c:
        project=c.post('/api/projects/upload?filename=retry.zip',content=payload({'a.py':'def f(): pass'})).json()
        store.update(project['id'],status='extraction_failed')
        response=c.post(f"/api/projects/{project['id']}/extract")
        assert response.status_code==200
        jobs.extract.assert_called_with(project['id'])
