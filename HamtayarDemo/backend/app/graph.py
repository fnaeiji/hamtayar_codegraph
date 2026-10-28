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

def neighborhood(index, symbol=None, relation=None):
    rows=query('MATCH (a:HamtayarEntity)-[r:HAMTAYAR_LINK]->(b:HamtayarEntity) WHERE a.index=$index AND b.index=$index AND ($symbol IS NULL OR a.id=$symbol OR b.id=$symbol) AND ($relation IS NULL OR r.kind=$relation) RETURN properties(a) AS a, properties(b) AS b,r.kind AS kind LIMIT 301',index=index,symbol=symbol,relation=relation)
    nodes={n['id']:n for row in rows[:300] for n in (row['a'],row['b'])}
    return {'nodes':list(nodes.values()),'edges':[{'source':r['a']['id'],'target':r['b']['id'],'kind':r['kind']} for r in rows[:300]],'truncated':len(rows)>300}
