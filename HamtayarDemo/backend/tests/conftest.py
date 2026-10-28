import os
import tempfile
os.environ["HAMTAYAR_RUNTIME"]=tempfile.mkdtemp(prefix="hamtayar-tests-")
import pytest
from app import graph

class PublicationDB:
    """Lazy stream/destination stand-in; does not execute Cypher."""
    def __init__(self,root):
        self.root=root;self.total=1;self.declarations=1;self.edge_total=0;self.extra=False
        self.node_batches=[];self.edge_batches=[];self.written={};self.relations={};self.calls=[];self.yielded=0
        self.fail_edges=False;self.max_ahead=0;self.closed=0
    def factory(self,staging=False):
        outer=self
        class DB:
            def __enter__(self): return self
            def __exit__(self,*args):outer.closed+=1
            def stream(self,q,**params):
                outer.calls.append((q,params))
                if 'properties(n) AS props' in q:
                    for i in range(outer.total):
                        outer.yielded+=1;outer.max_ahead=max(outer.max_ahead,outer.yielded-sum(outer.node_batches))
                        yield {'id':str(i),'labels':['Function'],'props':{'name':f'f{i}','path':outer.root+'/src/a.py','line_number':1,'end_line':2}}
                else:
                    for i in range(outer.edge_total):
                        yield {'a':str(i%outer.total),'b':'shared' if outer.extra else str((i+1)%outer.total),'kind':f'CALLS{i//outer.total}',
                               'extra_a':None,'extra_b':{'id':'shared','labels':['Module'],'props':{'name':'common'}} if outer.extra else None}
            def run(self,q,**params):
                outer.calls.append((q,params))
                if staging:return [{'total':outer.total,'declarations':outer.declarations}]
                if 'MERGE (n:HamtayarEntity' in q:
                    rows=params['rows'];outer.node_batches.append(len(rows))
                    for row in rows:outer.written.setdefault(row['index'],{})[row['id']]=row
                elif 'HAMTAYAR_LINK {kind:' in q:
                    if outer.fail_edges:raise ValueError('Injected destination failure')
                    outer.edge_batches.append(len(params['rows']))
                    for row in params['rows']:
                        for idx,nodes in outer.written.items():
                            if row['a'] in nodes and row['b'] in nodes:outer.relations.setdefault(idx,set()).add((row['a'],row['b'],row['kind']))
                elif 'count(r)' in q:return [{'total':len(outer.relations.get(params['index'],set()))}]
                elif 'count(n)' in q:return [{'total':len(outer.written.get(params['index'],{}))}]
                return []
        return DB()

@pytest.fixture
def publication_db(monkeypatch,tmp_path):
    db=PublicationDB(tmp_path.as_posix());monkeypatch.setattr(graph,'Graph',db.factory)
    return db
