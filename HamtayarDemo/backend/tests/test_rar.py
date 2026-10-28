import base64
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import rarfile
from fastapi.testclient import TestClient
from app import archive, rar_support
from app.main import app

FIXTURES=Path(__file__).parent/'fixtures'
def fixture(name):
    return base64.b64decode((FIXTURES/(name+'.b64')).read_text())

def test_real_stored_rar_upload_and_source():
    with TestClient(app) as client:
        response=client.post('/api/projects',files={'file':('source.rar',fixture('rar3-readonly-win.rar'))})
        assert response.status_code==200,response.text
        project=response.json()
        assert project['source_type']=='rar'
        assert project['status']=='ready_to_index'
        assert project['files'][0]['path']=='ro_dir/ro_file.txt'
        source=client.get(f"/api/projects/{project['id']}/source",params={'path':'ro_dir/ro_file.txt'})
        assert source.json()['text']=='readonly\n'

def test_format_from_bytes_not_filename():
    with TestClient(app) as client:
        response=client.post('/api/projects',files={'file':('misleading.zip',fixture('rar3-readonly-win.rar'))})
        assert response.json()['source_type']=='rar'

def test_real_compressed_rar_missing_decoder(monkeypatch):
    monkeypatch.setattr(rar_support,'configure',lambda:{'available':False})
    with TestClient(app) as client:
        response=client.post('/api/projects',files={'file':('compressed.rar',fixture('rar5-crc.rar'))})
        assert response.status_code==400
        assert 'UnRAR or 7-Zip' in response.json()['detail']

def test_invalid_rar_is_client_error():
    with TestClient(app) as client:
        for data in (b'not a rar',b'Rar!\x1a\x07\x00broken',b'Rar!\x1a\x07\x01\x00broken'):
            assert client.post('/api/projects',files={'file':('bad.rar',data)}).status_code==400

def entry(name='src/a.py',data=b'def f(): pass\n',**changes):
    attrs=dict(filename=name,file_size=len(data),volume=0,flags=0,file_redir=None,compress_type=rarfile.RAR_M0,
               is_dir=lambda:False,is_file=lambda:True,is_symlink=lambda:False,needs_password=lambda:False)
    attrs.update(changes)
    return SimpleNamespace(**attrs)

def fake_rar(monkeypatch,entries,password=False):
    reader=Mock()
    reader.__enter__=Mock(return_value=reader)
    reader.__exit__=Mock(return_value=False)
    reader.infolist.return_value=entries
    reader.needs_password.return_value=password
    reader.volumelist.return_value=['source.rar']
    reader.open.side_effect=lambda e:io.BytesIO(b'def f(): pass\n')
    monkeypatch.setattr(rar_support.rarfile,'RarFile',lambda *a,**k:reader)
    monkeypatch.setattr(rar_support,'configure',lambda:{'available':True})
    return reader

@pytest.mark.parametrize('item',[
    entry('../escape.py'),entry('C:/escape.py'),entry('a.py:stream'),
    entry(is_symlink=lambda:True),entry(file_redir=(1,0,'a')),
    entry(volume=1),entry(flags=rarfile.RAR_FILE_SPLIT_AFTER),
    entry(needs_password=lambda:True),entry(file_size=archive.MAX_FILE+1),
])
def test_rejected_before_decoder_opens_file(monkeypatch,tmp_path,item):
    reader=fake_rar(monkeypatch,[item])
    with pytest.raises(ValueError):
        rar_support.read_rar(tmp_path/'source.rar',tmp_path,archive._consume)
    reader.open.assert_not_called()

def test_actual_size_limit(monkeypatch,tmp_path):
    reader=fake_rar(monkeypatch,[entry(file_size=1)])
    with pytest.raises(ValueError,match='size does not match'):
        rar_support.read_rar(tmp_path/'source.rar',tmp_path,archive._consume)

def test_password_archive_rejected(monkeypatch,tmp_path):
    reader=fake_rar(monkeypatch,[],password=True)
    with pytest.raises(ValueError,match='Password-protected'):
        rar_support.read_rar(tmp_path/'source.rar',tmp_path,archive._consume)
    reader.open.assert_not_called()

def test_rar_capabilities_have_no_passwords():
    with TestClient(app) as client:
        result=client.get('/api/archives/capabilities')
        assert result.status_code==200
        assert result.json()['formats']==['zip','rar']
        assert not result.json()['rar_encrypted']
