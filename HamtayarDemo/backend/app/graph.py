"""CGC writes to isolated staging. Only namespaced copies reach the user's DB."""
import hashlib
import json
from neo4j import GraphDatabase, Query
from .config import setting

class Graph:
    def __init__(self, staging=False):
        prefix = 'STAGING_' if staging else ''
        uri = setting(prefix+'NEO4J_URI', 'bolt://127.0.0.1:7689' if staging else 'bolt://127.0.0.1:7687')
        password = setting(prefix+'NEO4J_PASSWORD')
        self.driver = GraphDatabase.driver(uri, auth=(setting(prefix+'NEO4J_USERNAME','neo4j'), password), connection_timeout=5)
        self.database = setting(prefix+'NEO4J_DATABASE','neo4j')
    def run(self, query, **params):
        try:
            with self.driver.session(database=self.database) as s:
                return s.run(Query(query, timeout=15), **params).data()
        finally:
            self.driver.close()

def query(text, staging=False, **params):
    return Graph(staging).run(text, **params)

def publish(project, index, workspace):
    # Global Module/ExternalClass nodes are shared in CGC. Snapshot their properties,
    # not their identity, into this version. Never copy edges to another path's code.
    prefix = workspace.resolve().as_posix() + '/'
    nodes = query('MATCH (n) WHERE n.path=$root OR n.path STARTS WITH $prefix RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props LIMIT 50001', True, root=prefix[:-1], prefix=prefix)
    if not nodes or len(nodes) > 50000:
        raise ValueError('No graph data or staging graph exceeds 50000-node demo limit')
    owned = {n['id'] for n in nodes}
    edges = query('MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids OR elementId(b) IN $ids RETURN elementId(a) AS a, elementId(b) AS b, type(r) AS type LIMIT 100001', True, ids=list(owned))
    if len(edges) > 100000:
        raise ValueError('Graph exceeds 100000-edge demo limit')
    extra = list({e[k] for e in edges for k in ('a','b')} - owned)
    if extra:
        nodes += query('MATCH (n) WHERE elementId(n) IN $ids AND n.path IS NULL RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props LIMIT 10001', True, ids=extra)
    if len(nodes) > 50000:
        raise ValueError('Graph exceeds demo limit')
    mapping = {n['id']: hashlib.sha256((index+':'+n['id']).encode()).hexdigest() for n in nodes}
    rows=[]
    for n in nodes:
        props=n['props']; path=str(props.get('path','')); relative=path[len(prefix):] if path.startswith(prefix) else ''
        # Keep a compact, browser-safe property representation.
        rows.append({'id':mapping[n['id']], 'project':project,'index':index,'name':str(props.get('name', n['labels'][0])), 'kind':n['labels'][0], 'path':relative,'line':int(props.get('line_number',props.get('start_line',1)) or 1), 'end':int(props.get('end_line',props.get('line_number',1)) or 1),'properties':json.dumps(props,default=str)})
    if not any(r['kind'] in ('Function','Class','Interface','Struct') for r in rows):
        raise ValueError('CGC produced no usable code declarations')
    for start in range(0,len(rows),500):
        query('UNWIND $rows AS row MERGE (n:HamtayarEntity {id:row.id}) SET n += row', rows=rows[start:start+500])
    rels=[{'a':mapping[e['a']],'b':mapping[e['b']],'kind':e['type']} for e in edges if e['a'] in mapping and e['b'] in mapping]
    for start in range(0,len(rels),500):
        query('UNWIND $rows AS row MATCH (a:HamtayarEntity {id:row.a}), (b:HamtayarEntity {id:row.b}) MERGE (a)-[:HAMTAYAR_LINK {kind:row.kind}]->(b)', rows=rels[start:start+500])
    return {'nodes':len(rows),'relationships':len(rels)}

def search(index, term='', limit=100):
    return query('MATCH (n:HamtayarEntity) WHERE n.index=$index AND (toLower(n.name) CONTAINS toLower($term) OR toLower(n.path) CONTAINS toLower($term)) RETURN properties(n) AS node ORDER BY n.path,n.line LIMIT $limit', index=index,term=term,limit=limit)

def neighborhood(index, symbol=None, relation=None):
    rows=query('MATCH (a:HamtayarEntity)-[r:HAMTAYAR_LINK]->(b:HamtayarEntity) WHERE a.index=$index AND b.index=$index AND ($symbol IS NULL OR a.id=$symbol OR b.id=$symbol) AND ($relation IS NULL OR r.kind=$relation) RETURN properties(a) AS a, properties(b) AS b,r.kind AS kind LIMIT 301',index=index,symbol=symbol,relation=relation)
    nodes={n['id']:n for row in rows[:300] for n in (row['a'],row['b'])}
    return {'nodes':list(nodes.values()),'edges':[{'source':r['a']['id'],'target':r['b']['id'],'kind':r['kind']} for r in rows[:300]],'truncated':len(rows)>300}
