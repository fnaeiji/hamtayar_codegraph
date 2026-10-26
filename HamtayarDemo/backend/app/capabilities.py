SUPPORTED={
'index':'ZIP workspace ingestion with isolated staging',
'update':'Reindex uploaded snapshot; publish only after validation',
'list':'Project dashboard', 'stats':'Project graph counts',
'find':'Scoped identifier/path and source text search',
'analyze':'Scoped direct callers/callees, imports and inheritance via graph relation filters',
'query':'Fixed parameterized templates only; arbitrary Cypher is rejected',
'visualize':'Interactive version-scoped graph',
'diagram':'Download current subgraph as JSON',
'config':'Environment settings and connection diagnostics',
'doctor':'Connectivity and CGC help diagnostics','version':'Runtime CGC version',
}
OTHER={'report':'Advanced report not yet adapted to project scope','bundle':'Upstream bundle operations not yet adapted','watch':'Immutable ZIP versions cannot be watched','unwatch':'No live-directory workflow','watching':'No live-directory workflow','context':'Managed by application project/version selector','setup-scip':'Compiler-backed indexing is disabled for uploaded code','add-package':'Installing dependencies from uploaded code is disabled','hook':'ZIP uploads are not Git working copies','registry':'Remote downloads are not part of local ZIP workflow','datasource':'Not implemented for the ZIP code demo','simulate':'Not yet adapted to project scope','mcp':'Use the documented context HTTP endpoint; MCP server not implemented','api':'Application uses its own bounded FastAPI endpoints','delete':'Disabled until safe scoped cleanup is implemented','clean':'Global cleanup could affect unrelated graph data'}
def manifest():
    return [{'command':k,'available':True,'detail':v} for k,v in SUPPORTED.items()]+[{'command':k,'available':False,'detail':v} for k,v in OTHER.items()]
