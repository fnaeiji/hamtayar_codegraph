import pytest
from fastapi.testclient import TestClient
from app import graph,store
from app.main import app

@pytest.fixture
def topology(monkeypatch):
    nodes={x:{'id':x,'name':x,'kind':'Class' if x in ('c','b','i') else 'Function','index':'owned'} for x in ['c','m','d','e','b','i']}
    nodes['foreign']={'id':'foreign','index':'another'}
    edges=[('c','m','CONTAINS'),('c','b','INHERITS'),('m','d','CALLS'),('d','e','USES'),('e','c','CYCLE'),('c','foreign','CALLS')]
    calls=[]
    def query(q,**params):
        calls.append((q,params))
        if ' AS node' in q:
            n=nodes.get(params['symbol'])
            return [{'node':n}] if n and n['index']==params['index'] else []
        frontier=params.get('frontier',[]);rows=[]
        for a,b,kind in edges:
            if nodes[a]['index']!=params['index'] or nodes[b]['index']!=params['index']:continue
            if params.get('relation') and kind not in params['relation_kinds']:continue
            if '(s)-[r:HAMTAYAR_LINK]-(t' in q: match=a in frontier or b in frontier
            elif '(s)-[r:HAMTAYAR_LINK]->(t' in q:match=a in frontier
            elif '(s)<-[r:HAMTAYAR_LINK]-(t' in q:match=b in frontier
            else:match=True
            if match:rows.append({'a':nodes[a],'b':nodes[b],'kind':kind})
        return rows[:params['limit']]
    monkeypatch.setattr(graph,'query',query)
    return calls

@pytest.mark.parametrize('depth,expected',[(1,{'c','m','b'}),(2,{'c','m','b','d'}),(3,{'c','m','b','d','e'}),(5,{'c','m','b','d','e'})])
def test_outgoing_depth_and_cycles(topology,depth,expected):
    result=graph.neighborhood('owned','c',depth=depth,direction='outgoing')
    assert {n['id'] for n in result['nodes']}==expected
    assert not result['truncated']
    assert len(topology)<=depth+1

@pytest.mark.parametrize('direction,expected',[('incoming',{'c','e'}),('both',{'c','m','b','e'})])
def test_direction_keeps_real_arrow(topology,direction,expected):
    result=graph.neighborhood('owned','c',direction=direction)
    assert {n['id'] for n in result['nodes']}==expected
    assert {'source':'e','target':'c','kind':'CYCLE'} in result['edges']


def test_isolated_and_filtered_root_remains_visible(topology):
    assert len(graph.neighborhood('owned','i')['nodes'])==1
    result=graph.neighborhood('owned','c',relation='CALLS',direction='outgoing',depth=3)
    assert [n['id'] for n in result['nodes']]==['c'] and not result['edges']


def test_foreign_or_stale_root_rejected(topology):
    with pytest.raises(ValueError,match='active project index'):graph.neighborhood('owned','foreign')

@pytest.mark.parametrize('bounds',[{'max_nodes':2},{'max_edges':1}])
def test_caps_are_explicit(topology,bounds):
    result=graph.neighborhood('owned','c',depth=5,**bounds)
    assert result['truncated']
    assert len(result['nodes'])<=bounds.get('max_nodes',200)
    assert len(result['edges'])<=bounds.get('max_edges',300)
    assert {e['source'] for e in result['edges']} <= {n['id'] for n in result['nodes']}
    assert {e['target'] for e in result['edges']} <= {n['id'] for n in result['nodes']}


def test_api_bounds_and_depth(topology):
    store.save({'id':'nav-test','active_index':'owned','status':'ready','files':[]})
    with TestClient(app) as client:
        url='/api/projects/nav-test/graph'
        r=client.get(url,params={'symbol':'c','depth':3,'direction':'outgoing'})
        assert r.status_code==200 and len(r.json()['nodes'])==5
        assert client.get(url,params={'depth':6}).status_code==422
        assert client.get(url,params={'direction':'arbitrary'}).status_code==400


def test_kind_filter_is_strict_without_inventing_links(topology):
    result=graph.neighborhood('owned','c',depth=3,kinds='Class',direction='outgoing')
    assert {n['id'] for n in result['nodes']}=={'c','b'}
    assert result['edges']==[{'source':'c','target':'b','kind':'INHERITS'}]
    assert result['hidden_nodes']>0
    functions=graph.neighborhood('owned','c',depth=3,kinds='Function',direction='outgoing')
    assert functions['root_filtered'] and all(n['kind']=='Function' for n in functions['nodes'])


def test_inheritance_preset(topology):
    result=graph.neighborhood('owned','c',relation='@inheritance',direction='outgoing')
    assert {n['id'] for n in result['nodes']}=={'c','b'}
