# Data flow and boundaries

Browser → same-origin Vite proxy → FastAPI → bounded ZIP extraction → immutable workspace + SQLite metadata → single background worker → CGC child interpreter → isolated staging Neo4j → validated namespaced destination graph → scoped search/graph/context endpoints.

LLM adapter uses chat/completions with evidence-only messages. It has no executable tools. Invalid evidence IDs reject model output. Evidence is retained on provider failures. Code and answer rendering use React text nodes, never raw HTML.

`archive.py`: path validation and source access. `cgc.py`: argv-only child execution and cancellation. `graph.py`: driver lifetime, publication and project-scoped queries. `jobs.py`: persisted state transitions, restart reconciliation and publication pointer. `store.py`: SQLite serialization/repository seam. `main.py`: typed HTTP API and settings. Frontend API, graph component, page layout and styles are separate.

Scoping: external staging node IDs are hashed together with an index attempt. Shared upstream name nodes are copied per attempt. Only edges with both copied endpoints are published. No upstream database-wide query or CLI analysis output is exposed unfiltered. Source paths in destination are relative to retained uploads. Existing graph labels are untouched. Query input selects fixed parameterized templates; it is never executed as Cypher.

Publication is not a cross-database transaction. Nodes/edges are written idempotently for an attempt, then SQLite active_index changes only after successful completion. Failures leave inactive artifacts. SQLite and runtime must be backed up together. Single-process mode is mandatory.
