import json
import threading
from unittest.mock import Mock
import pytest
from app import graph, config, store
from app.jobs import Jobs


def test_above_old_caps_streams_bounded_batches(publication_db,tmp_path,monkeypatch):
    monkeypatch.setitem(config.values,'GRAPH_PUBLISH_BATCH_SIZE','500')
    publication_db.total=50501;publication_db.edge_total=100501
    assert graph.publish('large','generation',tmp_path)=={'nodes':50501,'relationships':100501}
    assert max(publication_db.node_batches)<=500 and max(publication_db.edge_batches)<=500
    assert publication_db.max_ahead<=500 and publication_db.closed==2
    assert all('LIMIT 50001' not in q and 'LIMIT 100001' not in q for q,p in publication_db.calls)


def test_empty_graph_error_is_distinct(publication_db,tmp_path):
    publication_db.total=0;publication_db.declarations=0
    with pytest.raises(ValueError,match='Staging graph is empty'):graph.publish('p','v',tmp_path)
    assert not publication_db.written


def test_node_cap_has_count_and_setting(publication_db,tmp_path,monkeypatch):
    monkeypatch.setitem(config.values,'GRAPH_MAX_NODES','1');publication_db.total=2
    with pytest.raises(ValueError,match='2 selected nodes; GRAPH_MAX_NODES=1'):graph.publish('p','v',tmp_path)
    assert not publication_db.written


def test_shared_entities_and_scope(publication_db,tmp_path):
    publication_db.extra=True;publication_db.edge_total=5
    assert graph.publish('p','v',tmp_path,selected_paths=[tmp_path.as_posix()+'/src/a.py'])['nodes']==2
    q=next(q for q,p in publication_db.calls if 'extra_a' in q)
    assert 'a.path IS NULL' in q and 'b.path IS NULL' in q
    assert 'a.path IN $paths' in q and 'b.path IN $paths' in q


def test_shared_nodes_obey_total_cap(publication_db,tmp_path,monkeypatch):
    monkeypatch.setitem(config.values,'GRAPH_MAX_NODES','1');publication_db.extra=True;publication_db.edge_total=1
    with pytest.raises(ValueError,match='including shared entities'):graph.publish('p','v',tmp_path)


def test_edge_cap_never_silently_truncates(publication_db,tmp_path,monkeypatch):
    monkeypatch.setitem(config.values,'GRAPH_MAX_RELATIONSHIPS','1');publication_db.edge_total=2
    with pytest.raises(ValueError,match='GRAPH_MAX_RELATIONSHIPS=1'):graph.publish('p','v',tmp_path)


def test_cancel_closes_connections(publication_db,tmp_path):
    event=threading.Event()
    def log(message):
        if message.startswith('Preparing'):event.set()
    with pytest.raises(ValueError,match='Cancelled'):graph.publish('p','v',tmp_path,cancelled=event,log=log)
    assert publication_db.closed==2


def test_retry_skips_cgc_and_preserves_old_index_on_failure(monkeypatch,tmp_path,publication_db):
    import app.jobs as module
    from app.cgc import CGCAdapter
    monkeypatch.setattr(module,'RUNTIME',tmp_path)
    root=tmp_path/'workspaces'/'retry-p'/'source';root.mkdir(parents=True);publication_db.root=root.as_posix()
    report=tmp_path/'cgc'/'completed';report.mkdir(parents=True)
    (report/'report.json').write_text(json.dumps({'outcome':'completed','selected':[root.as_posix()+'/src/a.py'],'skipped':[]}))
    store.save({'id':'retry-p','status':'failed','job':'completed','files':[{'excluded':False}],'active_index':'old','logs':[]})
    index=Mock();monkeypatch.setattr(CGCAdapter,'index',index)
    worker=Jobs()
    try:
        worker.run('retry-p','new',threading.Event(),report_job='completed')
        assert store.get('retry-p')['active_index']=='new' and store.get('retry-p')['status']=='ready'
        publication_db.fail_edges=True;publication_db.edge_total=1
        worker.run('retry-p','broken',threading.Event(),report_job='completed')
        assert store.get('retry-p')['active_index']=='new' and store.get('retry-p')['status']=='failed'
    finally:worker.pool.shutdown()
    index.assert_not_called()


def test_retry_rejects_bad_reports(monkeypatch,tmp_path):
    import app.jobs as module
    monkeypatch.setattr(module,'RUNTIME',tmp_path)
    report=tmp_path/'cgc'/'j';report.mkdir(parents=True);worker=Jobs()
    try:
        for data in [{'outcome':'running','selected':['/elsewhere/a.py']},{'outcome':'completed','selected':['/elsewhere/a.py']}]:
            (report/'report.json').write_text(json.dumps(data))
            with pytest.raises(ValueError):worker.completed_report('p','j')
    finally:worker.pool.shutdown()


def test_retry_endpoint_queues_only_publication(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app,jobs
    from app.uploads import public_project
    store.save({'id':'publish-endpoint','status':'failed','files':[],'logs':[]})
    submit=Mock();monkeypatch.setattr(jobs,'submit',submit)
    with TestClient(app) as client:
        response=client.post('/api/projects/publish-endpoint/publish')
    assert response.status_code==200
    submit.assert_called_once_with('publish-endpoint',publish_only=True)
