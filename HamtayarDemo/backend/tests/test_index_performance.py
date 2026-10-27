import json
import os
import subprocess
import sys
import importlib.util
from pathlib import Path
import pytest
from app import config, graph, store
from app.index_policy import exclusion, preview, settings
from app.cgc_runner import Monitor
from app.main import index_preview, index_report


def test_policy_lists_large_and_generated_files_without_deleting(monkeypatch):
    monkeypatch.setitem(config.values,'INDEX_MAX_FILE_MB','2')
    monkeypatch.setitem(config.values,'INDEX_EXCLUDE_GLOBS','*.min.js,stimulsoft*.js')
    files=[{'path':'src/a.py','size':20,'excluded':False},
           {'path':'web/stimulsoft.reports.js','size':20,'excluded':False},
           {'path':'src/large.cs','size':3*1024**2,'excluded':False}]
    result=preview(files)
    assert result['eligible_files']==1 and result['skipped_count']==2
    assert files[1]['excluded'] is False
    assert result['skipped'][0]['reason']=='INDEX_EXCLUDE_GLOBS: stimulsoft*.js'
    monkeypatch.setitem(config.values,'INDEX_MAX_FILE_MB','0')
    monkeypatch.setitem(config.values,'INDEX_EXCLUDE_GLOBS','-')
    assert preview(files)['eligible_files']==3

@pytest.mark.parametrize('key,value',[('INDEX_PARALLEL_WORKERS','0'),('INDEX_TIMEOUT_SECONDS','bad'),('INDEX_MAX_FILE_MB','nan')])
def test_bad_index_limits_fail_before_start(monkeypatch,key,value):
    monkeypatch.setitem(config.values,key,value)
    with pytest.raises(ValueError):settings()


def test_monitor_tracks_active_and_slow_operations_on_failure():
    monitor=Monitor({})
    def broken(path):
        status=monitor.snapshot()
        assert status['active'][0]['path']=='src/example.py'
        assert status['active'][0]['stage']=='parse'
        raise RuntimeError('failed')
    with pytest.raises(RuntimeError):monitor.wrap('parse',broken,0)('src/example.py')
    status=monitor.snapshot()
    assert status['active']==[] and status['completed_operations']['parse']==1
    assert status['slowest'][0]['path']=='src/example.py'


def test_publish_scopes_to_current_selected_paths(monkeypatch,tmp_path):
    calls=[];root=tmp_path.as_posix()
    def query(q,staging=False,**params):
        calls.append((q,params))
        if 'properties(n) AS props' in q:
            return [{'id':'1','labels':['Function'],'props':{'name':'f','path':root+'/src/a.py'}}]
        return []
    monkeypatch.setattr(graph,'query',query)
    graph.publish('p','v',tmp_path,selected_paths=[root+'/src/a.py'])
    q,params=calls[0]
    assert 'n.path IN $paths' in q and params['scoped']
    assert root+'/src/a.py' in params['paths'] and root+'/src' in params['paths']
    assert root+'/vendor.js' not in params['paths']


def test_preview_and_report_keep_responses_bounded(monkeypatch,tmp_path):
    import app.main as api
    monkeypatch.setattr(api,'RUNTIME',tmp_path)
    store.save({'id':'perf-report','job':'j','status':'indexing','files':[]})
    assert index_report('perf-report')['available'] is False
    path=tmp_path/'cgc'/'j';path.mkdir(parents=True)
    (path/'report.json').write_text(json.dumps({'selected':['a']*500,'skipped':[{'path':'b'}]*400}))
    result=index_report('perf-report')
    assert len(result['selected'])==20 and result['selected_count']==500
    assert len(result['skipped'])==100 and result['skipped_count']==400
    assert index_preview('perf-report')['eligible_files']==0


@pytest.mark.parametrize('missing_parser',[False,True])
def test_real_cgc_runner_with_mock_database(tmp_path,missing_parser):
    # Optional integration: real CGC discovery/parsing/resolution; persistence mocked.
    if importlib.util.find_spec('codegraphcontext') is None:pytest.skip('Install codegraphcontext==0.6.13 for bridge integration test')
    source=tmp_path/'source';source.mkdir()
    (source/'a.cs').write_text('class Hello { public int Value() { return 42; } }')
    (source/'vendor.min.js').write_text('function ignored() {}')
    policy=tmp_path/'policy.json';policy.write_text(json.dumps({'max_bytes':2048,'patterns':['*.min.js']}))
    report=tmp_path/'report.json'
    runner=Path(__file__).resolve().parents[1]/'app'/'cgc_runner.py'
    script='''
import asyncio, os, runpy, sys
from pathlib import Path
from unittest.mock import MagicMock
from types import SimpleNamespace
Path.home=classmethod(lambda cls:Path(os.environ['HAMTAYAR_CGC_PROFILE']))
from codegraphcontext.cli import cli_helpers
from codegraphcontext.tools.graph_builder import GraphBuilder
from codegraphcontext.core.jobs import JobManager
# Supply the installed native C# grammar to avoid runtime parser downloads.
from tree_sitter import Language, Parser
import tree_sitter_c_sharp
from codegraphcontext.utils.tree_sitter_manager import TreeSitterManager
language=Language(tree_sitter_c_sharp.language())
TreeSitterManager.get_language_safe=lambda self,name:language
TreeSitterManager.create_parser=lambda self,name:Parser(language)
builder=GraphBuilder(MagicMock(),JobManager(),asyncio.new_event_loop())
builder._writer=MagicMock()
if os.environ.get('TEST_MISSING_PARSER')=='1': builder.get_parser=lambda ext:None
cli_helpers._initialize_services=lambda **kw: (MagicMock(),builder,MagicMock(),SimpleNamespace(cgcignore_path=None))
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
    env={**os.environ,'HAMTAYAR_CGC_PROFILE':str(tmp_path/'profile'),'CGC_IGNORE_PROJECT_ENV':'1',
         'ENABLE_APP_LOGS':'INFO','SCIP_INDEXER':'false','PARALLEL_WORKERS':'2','TEST_MISSING_PARSER':'1' if missing_parser else '0'}
    p=subprocess.run([sys.executable,'-c',script,str(runner),str(source),str(policy),str(report)],env=env,capture_output=True,text=True,timeout=90)
    result=json.loads(report.read_text())
    if missing_parser:
        assert p.returncode!=0 and result['outcome']=='failed'
        assert result['unparsed'][0]['path'].endswith('a.cs')
        return
    assert p.returncode==0,p.stdout+'\n'+p.stderr
    assert result['outcome']=='completed'
    assert any(p.endswith('/a.cs') for p in result['selected'])
    assert result['skipped'][0]['path']=='vendor.min.js'
    assert result['summary']['class_nodes']>=1
    assert result['performance']['completed_operations']['parse']>=1
