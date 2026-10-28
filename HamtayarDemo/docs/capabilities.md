# Capability inventory

Basis: repository Git-link commit 93c9685bff9151f50a3121e9913e5ba2d27c1191, inspected graph writer/config manager and user-provided CLI help. Runtime Settings fetches actual version and index/find/analyze help. Full parser/analysis parity has not been independently validated.

| Family | UI/integration | Status |
|---|---|---|
| index | ZIP preview, background CGC indexing into staging | Implemented; live Neo4j validation required locally |
| update | New attempt for immutable uploaded source | Implemented, not live Git update |
| list/stats | Dashboard; version-scoped graph counts | Implemented |
| find | Identifier/path and literal source-text search | Implemented subset, not regex/decorator/argument parity |
| analyze | Selected node's direct relations; CALLS/IMPORTS/INHERITS filters | Implemented subset; no complexity/dead-code/shortest-path claims |
| query | Parameterized symbols, relationships and stats | Implemented; free Cypher disabled |
| visualize | Cytoscape selection, zoom, fit, direct-neighbor expansion | Implemented |
| diagram | JSON export of visible subgraph | Partial; no Mermaid/DOT yet |
| config | Local settings form, no upstream global mutation | Implemented application scope |
| doctor/version | Neo4j connection test and real executable diagnostics | Implemented |
| report/bundle | Upstream output needs safe scoping adapter | Not implemented |
| watch/unwatch/watching | Requires mutable live-directory workflow | Not applicable to ZIP snapshots |
| context | Application-owned selection | Replaces upstream workspace management in UI |
| setup-scip/add-package | Builds and dependency execution | Disabled for uploaded code |
| hook | Requires a Git working copy | Not applicable |
| registry/datasource/simulate | Additional service/domain workflows | Not implemented |
| mcp | HTTP context endpoint available; no MCP server | Not implemented |
| api | Separate FastAPI application | Implemented alternative |
| delete/clean | Existing destination data must be protected | Disabled until scoped cleanup exists |

Enabled buttons map to actual application operations, not arbitrary CLI passthrough. Unsupported families are visible with reasons. CLI wrappers are limited to index and diagnostics; safe retrieval uses the normalized published graph.
