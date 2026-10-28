"""Stream a selected CGC graph into a new, inactive destination generation."""
import hashlib
import json
from pathlib import Path
from contextlib import closing
from .config import setting

DECLARATIONS=('Function','Class','Interface','Struct')

def limits():
    result={}
    for key,default,minimum,maximum in [('GRAPH_MAX_NODES',1000000,1,10000000),('GRAPH_MAX_RELATIONSHIPS',5000000,1,50000000),('GRAPH_PUBLISH_BATCH_SIZE',500,1,2000),('GRAPH_QUERY_TIMEOUT_SECONDS',1800,30,86400)]:
        try: value=int(setting(key,str(default)))
        except ValueError: raise ValueError(f'{key} must be an integer') from None
        if not minimum<=value<=maximum: raise ValueError(f'{key} must be {minimum}..{maximum}')
        result[key]=value
    return result

def scope(workspace, selected_paths):
    root=workspace.resolve().as_posix(); prefix=root+'/'
    paths=set()
    if selected_paths is not None:
        for item in selected_paths:
            path=Path(item).resolve()
            if not path.is_relative_to(workspace.resolve()): raise ValueError('Index report contains a path outside this project')
            paths.add(path.as_posix())
            for parent in path.parents:
                if parent.as_posix()==root: break
                paths.add(parent.as_posix())
        paths.add(root)
    return {'root':root,'prefix':prefix,'scoped':selected_paths is not None,'paths':sorted(paths)}

def predicate(alias):
    return f'(({alias}.path=$root OR {alias}.path STARTS WITH $prefix) AND ($scoped=false OR {alias}.path IN $paths))'

def identity(index,eid): return hashlib.sha256((index+':'+eid).encode()).hexdigest()

def node_row(node,project,index,prefix):
    props=node['props']; labels=node['labels'];path=str(props.get('path',''))
    return {'id':identity(index,node['id']),'project':project,'index':index,
            'name':str(props.get('name',labels[0] if labels else 'Entity')),
            'kind':next((label for label in labels if label in DECLARATIONS),labels[0] if labels else 'Entity'),
            'path':path[len(prefix):] if path.startswith(prefix) else '',
            'line':int(props.get('line_number',props.get('start_line',props.get('function_line_number',1))) or 1),
            'end':int(props.get('end_line',props.get('line_number',props.get('function_line_number',1))) or 1),
            'properties':json.dumps(props,default=str)}

NODE_WRITE='UNWIND $rows AS row MERGE (n:HamtayarEntity {id:row.id}) SET n += row'
EDGE_WRITE='UNWIND $rows AS row MATCH (a:HamtayarEntity {id:row.a}), (b:HamtayarEntity {id:row.b}) MERGE (a)-[:HAMTAYAR_LINK {kind:row.kind}]->(b)'


def publish(project,index,workspace,selected_paths=None,cancelled=None,log=None):
    from .graph import Graph
    options=limits();params=scope(workspace,selected_paths);batch_size=options['GRAPH_PUBLISH_BATCH_SIZE']
    timeout=options['GRAPH_QUERY_TIMEOUT_SECONDS']; log=log or (lambda message:None)
    def check():
        if cancelled is not None and cancelled.is_set(): raise ValueError('Cancelled during graph publication')
    check()
    with Graph(True) as source, Graph() as destination:
        # Counts are separate from stream limits: never mistake truncation for success.
        stat=source.run(f'MATCH (n) WHERE {predicate("n")} RETURN count(n) AS total, sum(CASE WHEN any(label IN labels(n) WHERE label IN $declarations) THEN 1 ELSE 0 END) AS declarations',_timeout=timeout,**params,declarations=list(DECLARATIONS))[0]
        total=stat['total']; log(f'Staging graph: {total:,} selected nodes; {stat["declarations"]:,} code declarations.')
        if not total: raise ValueError('Staging graph is empty for this project and indexing scope. Check the completed CGC report and STAGING_NEO4J_DATABASE.')
        if not stat['declarations']: raise ValueError('CGC produced no usable code declarations in the selected graph')
        if total>options['GRAPH_MAX_NODES']:
            raise ValueError(f'Staging has {total:,} selected nodes; GRAPH_MAX_NODES={options["GRAPH_MAX_NODES"]:,}. Increase this publication setting or reduce indexing scope, then retry publication.')
        log('Preparing destination lookup indexes...')
        for prop in ('id','index'):
            destination.run(f'CREATE INDEX hamtayar_entity_{prop} IF NOT EXISTS FOR (n:HamtayarEntity) ON (n.{prop})',_timeout=timeout)
        destination.run('CALL db.awaitIndexes(300)',_timeout=max(timeout,330))
        check(); rows=[];size=0;processed=0
        with closing(source.stream(f'MATCH (n) WHERE {predicate("n")} RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props',_timeout=timeout,**params)) as stream:
            for node in stream:
                check();row=node_row(node,project,index,params['prefix']);rows.append(row);size+=len(row['properties'])
                if len(rows)>=batch_size or size>=4*1024**2:
                    destination.run(NODE_WRITE,rows=rows);processed+=len(rows);rows=[];size=0
                    log(f'Publishing nodes: {processed:,}/{total:,}')
            if rows: destination.run(NODE_WRITE,rows=rows);processed+=len(rows)
        if processed!=total: raise ValueError('Staging changed while publishing nodes; retry after all indexing stops')
        log(f'Publishing nodes: {processed:,}/{total:,}. Streaming relationships...')
        # Both endpoints must be selected code, or one selected and one pathless
        # shared CGC entity. Never copy another repository's path-bearing node.
        edge_query=f'''MATCH (a)-[r]->(b) WHERE
            ({predicate('a')} AND ({predicate('b')} OR b.path IS NULL)) OR
            (a.path IS NULL AND {predicate('b')})
            RETURN elementId(a) AS a, elementId(b) AS b, type(r) AS kind,
            CASE WHEN a.path IS NULL THEN {{id:elementId(a),labels:labels(a),props:properties(a)}} ELSE null END AS extra_a,
            CASE WHEN b.path IS NULL THEN {{id:elementId(b),labels:labels(b),props:properties(b)}} ELSE null END AS extra_b'''
        edges=[];extras={};size=0;processed_edges=0;node_upper=total
        def write_edges():
            nonlocal node_upper
            extra_rows=list(extras.values())
            for start in range(0,len(extra_rows),batch_size):
                destination.run(NODE_WRITE,rows=extra_rows[start:start+batch_size])
            node_upper+=len(extras)
            if edges: destination.run(EDGE_WRITE,rows=edges)
            # Check actual distinct destination nodes, including shared extras.
            if node_upper<=options['GRAPH_MAX_NODES']: return
            counts=destination.run('MATCH (n:HamtayarEntity) WHERE n.index=$index RETURN count(n) AS total',index=index)[0]['total']
            node_upper=counts
            if counts>options['GRAPH_MAX_NODES']:
                raise ValueError(f'Published generation has {counts:,} nodes including shared entities; GRAPH_MAX_NODES={options["GRAPH_MAX_NODES"]:,}. Increase the setting and retry publication.')
        with closing(source.stream(edge_query,_timeout=timeout,**params)) as stream:
            for edge in stream:
                check();processed_edges+=1
                if processed_edges>options['GRAPH_MAX_RELATIONSHIPS']:
                    raise ValueError(f'Graph exceeds GRAPH_MAX_RELATIONSHIPS={options["GRAPH_MAX_RELATIONSHIPS"]:,}; no partial generation activated. Increase the setting and retry publication.')
                for key in ('extra_a','extra_b'):
                    if edge[key]:
                        row=node_row(edge[key],project,index,params['prefix']);extras[row['id']]=row;size+=len(row['properties'])
                edges.append({'a':identity(index,edge['a']),'b':identity(index,edge['b']),'kind':edge['kind']})
                if len(edges)>=batch_size or size>=4*1024**2:
                    write_edges();log(f'Publishing relationships: {processed_edges:,}');edges=[];extras={};size=0
            write_edges()
        check()
        from .csharp_semantics import enrich
        semantic_summary=enrich(destination,project,index,workspace,selected_paths,cancelled,log)
        log('C# semantic enrichment: '+json.dumps(semantic_summary))
        check()
        counts=destination.run('MATCH (n:HamtayarEntity) WHERE n.index=$index RETURN count(n) AS total',index=index)[0]
        relations=destination.run('MATCH (a:HamtayarEntity)-[r:HAMTAYAR_LINK]->(b:HamtayarEntity) WHERE a.index=$index AND b.index=$index RETURN count(r) AS total',index=index)[0]
        if counts['total']>options['GRAPH_MAX_NODES'] or relations['total']>options['GRAPH_MAX_RELATIONSHIPS']:
            raise ValueError('Enriched graph exceeds GRAPH_MAX_NODES or GRAPH_MAX_RELATIONSHIPS; increase publication limits and retry. Partial output remains inactive.')
        log(f'Graph publication complete: {counts["total"]:,} nodes; {relations["total"]:,} relationships.')
        return {'nodes':counts['total'],'relationships':relations['total']}
