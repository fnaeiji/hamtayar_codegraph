"""CGC writes to isolated staging. Only namespaced copies reach the user's DB."""
import hashlib
import json
from neo4j import GraphDatabase, Query
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired, Neo4jError
from urllib.parse import urlsplit
from .config import setting

class Graph:
    def __init__(self, staging=False):
        self.staging = staging
        prefix = 'STAGING_' if staging else ''
        uri = setting(prefix+'NEO4J_URI', 'bolt://127.0.0.1:7689' if staging else 'bolt://127.0.0.1:7687')
        password = setting(prefix+'NEO4J_PASSWORD')
        self.driver = GraphDatabase.driver(uri, auth=(setting(prefix+'NEO4J_USERNAME','neo4j'), password), connection_timeout=5)
        self.database = setting(prefix+'NEO4J_DATABASE','neo4j')
    def __enter__(self): return self
    def __exit__(self, *exc): self.driver.close()
    def stream(self, text, _timeout=15, **params):
        try:
            with self.driver.session(database=self.database, fetch_size=500) as session:
                result=session.run(Query(text,timeout=_timeout),**params)
                for record in result:
                    yield record.data()
                result.consume()
        except (ServiceUnavailable, SessionExpired, Neo4jError) as exc:
            raise ValueError(connection_error(exc,self.staging)) from None
    def run(self, text, _timeout=15, **params):
        return list(self.stream(text,_timeout=_timeout,**params))

def connection_error(exc, staging=False):
    prefix = 'STAGING_' if staging else ''
    role = 'staging (CGC temporary database)' if staging else 'destination (published graph)'
    # Never interpolate exception text, URI credentials, query strings or passwords.
    uri = setting(prefix+'NEO4J_URI', 'bolt://127.0.0.1:7689' if staging else 'bolt://127.0.0.1:7687')
    try:
        parsed = urlsplit(uri)
        endpoint = f'{parsed.hostname}:{parsed.port or 7687}'
    except ValueError:
        endpoint = 'invalid URI'
    label = f'Neo4j {role} [{endpoint}]'
    if isinstance(exc, AuthError):
        return f'{label}: authentication failed. Check {prefix}NEO4J_USERNAME and {prefix}NEO4J_PASSWORD. Changing .env does not reset an existing database password.'
    if isinstance(exc, (ServiceUnavailable, SessionExpired)):
        action = 'From HamtayarDemo run: docker compose up -d staging; docker compose ps. ' if staging else 'Start your destination Neo4j container and check its published Bolt port. '
        return f'{label}: connection unavailable. {action}Check {prefix}NEO4J_URI and run the connection test again. Also check Docker logs and TLS settings if the port is reachable.'
    code = getattr(exc, 'code', '') or ''
    if code.endswith('DatabaseNotFound'):
        return f'{label}: database not found. Check {prefix}NEO4J_DATABASE.'
    return f'{label}: database operation failed. Check database availability, user permissions and server logs.'


def query(text, staging=False, **params):
    with Graph(staging) as db:
        return db.run(text, **params)

def publish(project, index, workspace, selected_paths=None, cancelled=None, log=None):
    from .publication import publish as stream_publish
    return stream_publish(project,index,workspace,selected_paths,cancelled,log)

def search(index, term='', limit=100):
    return query('MATCH (n:HamtayarEntity) WHERE n.index=$index AND (toLower(n.name) CONTAINS toLower($term) OR toLower(n.path) CONTAINS toLower($term)) RETURN properties(n) AS node ORDER BY n.path,n.line LIMIT $limit', index=index,term=term,limit=limit)

def neighborhood(index, symbol=None, relation=None, depth=1, direction='both', max_nodes=200, max_edges=300, kinds=None, hide_injected_fields=True):
    """Bounded breadth-first expansion, never an unbounded variable-length path."""
    if not 1<=depth<=5 or direction not in ('both','outgoing','incoming') or not 1<=max_nodes<=500 or not 1<=max_edges<=1000:
        raise ValueError('Graph bounds: depth 1..5, nodes 1..500, edges 1..1000; direction both/outgoing/incoming')
    if relation is not None and len(relation)>100: raise ValueError('Relationship filter is too long')
    kinds_set={part.strip() for part in (kinds or '').split(',') if part.strip()}
    if len(kinds_set)>12 or any(len(k)>40 or not k.replace('_','').isalnum() for k in kinds_set):raise ValueError('Invalid node kind filter')
    presets={'@inheritance':['INHERITS','INHERITS_FROM','EXTENDS','IMPLEMENTS','BASE_TYPE'],'@services':['INJECTS','USES_SERVICE','DECLARED_TYPE']}
    relation_kinds=presets.get(relation,[relation] if relation else [])
    nodes={};edges={};truncated=False;reasons=[];expanded=0
    if symbol:
        seed=query('MATCH (n:HamtayarEntity {id:$symbol}) WHERE n.index=$index RETURN n{.id,.name,.kind,.path,.line,.end,.index,.semantic_role,.declared_type,.resolution,.field_names} AS node LIMIT 1',symbol=symbol,index=index)
        if not seed: raise ValueError('Selected symbol is not in the active project index; search again')
        nodes[symbol]=seed[0]['node'];frontier=[symbol]
    else:
        frontier=[]
    for hop in range(depth if symbol else 1):
        if symbol and not frontier: break
        remaining=max_edges-len(edges)
        if remaining<=0: truncated=True;reasons.append('edge_limit');break
        if symbol:
            pattern={'outgoing':'(s)-[r:HAMTAYAR_LINK]->(t:HamtayarEntity)',
                     'incoming':'(s)<-[r:HAMTAYAR_LINK]-(t:HamtayarEntity)',
                     'both':'(s)-[r:HAMTAYAR_LINK]-(t:HamtayarEntity)'}[direction]
            text=('MATCH (s:HamtayarEntity) WHERE s.index=$index AND s.id IN $frontier '
                  'MATCH '+pattern+' WHERE t.index=$index '
                  'WITH startNode(r) AS a, endNode(r) AS b,r ')
        else:
            text='MATCH (a:HamtayarEntity)-[r:HAMTAYAR_LINK]->(b:HamtayarEntity) '
        rows=query(text+'WHERE a.index=$index AND b.index=$index AND ($relation IS NULL OR r.kind IN $relation_kinds) '
            'AND ($hide_fields=false OR (coalesce(a.semantic_role,"")<>"injected_field" AND coalesce(b.semantic_role,"")<>"injected_field")) '
            'RETURN a{.id,.name,.kind,.path,.line,.end,.index,.semantic_role,.declared_type,.resolution,.field_names} AS a, b{.id,.name,.kind,.path,.line,.end,.index,.semantic_role,.declared_type,.resolution,.field_names} AS b,r.kind AS kind,r.declared_type AS declared_type,r.origin AS origin,r.evidence_path AS evidence_path,r.line AS evidence_line LIMIT $limit',
            index=index,relation=relation,relation_kinds=relation_kinds,hide_fields=hide_injected_fields,frontier=frontier,limit=remaining+1)
        if len(rows)>remaining: truncated=True;reasons.append('edge_limit')
        next_frontier=[]
        for row in rows[:remaining]:
            a,b=row['a'],row['b'];key=(a['id'],b['id'],row['kind'])
            if key in edges:continue
            additions={n['id']:n for n in (a,b) if n['id'] not in nodes}
            if len(nodes)+len(additions)>max_nodes:
                truncated=True;reasons.append('node_limit');continue
            nodes.update(additions);next_frontier.extend(additions)
            edges[key]={'source':a['id'],'target':b['id'],'kind':row['kind'],**{k:row[k] for k in ('declared_type','origin','evidence_path','evidence_line') if row.get(k) is not None}}
        expanded=hop+1
        if truncated:break
        frontier=next_frontier
    displayed={id:n for id,n in nodes.items() if (not kinds_set or n.get('kind') in kinds_set) and (not hide_injected_fields or n.get('semantic_role')!='injected_field')}
    displayed_edges=[e for e in edges.values() if e['source'] in displayed and e['target'] in displayed]
    return {'nodes':list(displayed.values()),'edges':displayed_edges,'truncated':truncated,
            'kinds':sorted(kinds_set),'hidden_nodes':len(nodes)-len(displayed),'root_filtered':bool(symbol and symbol not in displayed),
            'hide_injected_fields':hide_injected_fields,
            'truncation_reasons':sorted(set(reasons)),'root':symbol,'depth':depth,
            'expanded_depth':expanded,'direction':direction,'relation':relation,
            'limits':{'nodes':max_nodes,'edges':max_edges},'mode':'neighborhood' if symbol else 'overview'}


def relationship_types(index):
    return query('MATCH (a:HamtayarEntity)-[r:HAMTAYAR_LINK]->(b:HamtayarEntity) '
                 'WHERE a.index=$index AND b.index=$index RETURN r.kind AS kind,count(r) AS total ORDER BY total DESC',index=index)


def node_kinds(index):
    return query('MATCH (n:HamtayarEntity) WHERE n.index=$index RETURN n.kind AS kind,count(n) AS total ORDER BY total DESC',index=index)
