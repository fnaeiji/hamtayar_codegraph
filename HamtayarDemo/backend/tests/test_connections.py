import os
import tempfile
os.environ.setdefault("HAMTAYAR_RUNTIME", tempfile.mkdtemp(prefix="hamtayar-connections-"))
import threading
from unittest.mock import MagicMock
import pytest
from neo4j.exceptions import AuthError, ServiceUnavailable
from app import graph, config, store
from app.jobs import Jobs
from app.main import connection

@pytest.mark.parametrize('stage', [True, False])
def test_connection_failure_names_target_without_secrets(monkeypatch, stage):
    prefix = 'STAGING_' if stage else ''
    monkeypatch.setitem(config.values, prefix+'NEO4J_URI', 'bolt://user:secret@localhost:7689?token=hidden')
    driver = MagicMock()
    driver.session.return_value.__enter__.side_effect = ServiceUnavailable('secret hidden internal details')
    monkeypatch.setattr(graph.GraphDatabase, 'driver', lambda *a, **kw: driver)
    with pytest.raises(ValueError) as error:
        graph.query('RETURN 1', stage)
    text = str(error.value)
    assert ('staging' if stage else 'destination') in text
    assert 'localhost:7689' in text
    assert 'secret' not in text and 'hidden' not in text
    driver.close.assert_called_once()

def test_auth_error_is_actionable():
    text = graph.connection_error(AuthError('private password'), True)
    assert 'STAGING_NEO4J_PASSWORD' in text
    assert 'does not reset' in text
    assert 'private password' not in text

def test_connection_test_reports_both_targets(monkeypatch):
    def query(q, stage):
        if stage:
            raise ValueError('Neo4j staging: connection unavailable')
        return [{'ok': 1}]
    monkeypatch.setattr(graph, 'query', query)
    result = connection()
    assert result['destination']['ok']
    assert result['staging']['error'] == 'Neo4j staging: connection unavailable'

def test_destination_preflight_prevents_cgc_and_logs_failure(monkeypatch):
    from app.cgc import CGCAdapter
    monkeypatch.setitem(config.values,'NEO4J_URI','bolt://127.0.0.1:7687')
    monkeypatch.setitem(config.values,'STAGING_NEO4J_URI','bolt://127.0.0.1:7689')
    calls=[]
    def query(q, stage):
        calls.append(stage)
        if not stage: raise ValueError('Neo4j destination: connection unavailable')
        return [{'ok':1}]
    monkeypatch.setattr(graph,'query',query)
    index=MagicMock(); monkeypatch.setattr(CGCAdapter,'index',index)
    store.save({'id':'preflight-test','status':'queued','logs':[],'active_index':'previous'})
    jobs=Jobs()
    try: jobs.run('preflight-test','new',threading.Event())
    finally: jobs.pool.shutdown()
    result=store.get('preflight-test')
    assert calls == [True,False]
    index.assert_not_called()
    assert result['status']=='failed' and result['active_index']=='previous'
    assert 'destination' in result['error']
    assert 'Indexing failed:' in result['logs'][-1]
