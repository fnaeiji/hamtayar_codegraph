# Hamtayar Code Intelligence

A local Persian/RTL React + FastAPI application for ZIP ingestion, CGC indexing, Neo4j graph exploration, source evidence, and optional OpenAI-compatible answers. Application code lives here; the upstream CGC checkout remains external.

## Windows quick start

Prerequisites: Python 3.12, Node 20+, Docker Desktop, and your working CGC environment.

```powershell
cd D:\CGC\HamtayarDemo
.\scripts\setup.ps1
notepad .env
# Set CGC_EXECUTABLE, destination Neo4j credentials, and a NEW staging password.
docker compose up -d
.\scripts\start-dev.ps1
.\scripts\smoke-test.ps1
```

Open **http://127.0.0.1:5173**. API documentation: http://127.0.0.1:8000/docs.

```powershell
.\scripts\stop-dev.ps1
```

If this folder is nested inside your cloned `hamtayar_codegraph` repository, use its actual path. Configure CGC_EXECUTABLE to your existing CGC executable. The tracked upstream Git link is not a vendored CGC installation; a fresh clone still needs a separately installed CGC environment. Inspect/test against upstream commit `93c9685bff9151f50a3121e9913e5ba2d27c1191` (observed user package version 0.6.13). Do not automatically upgrade it.

## Why a second Neo4j instance?

The inspected CGC writer uses global name-only MERGE keys for Module, DbTable, and ExternalClass. Its unmodified indexing pipeline is therefore not safe to run against your populated destination as if it supplied project isolation.

Docker Compose starts **only staging** on Bolt 7689 / Browser 7476. Your destination stays on 7687. CGC writes into staging. The app reads owned path nodes and adjacent pathless shared declarations, then publishes namespaced `HamtayarEntity` nodes and `HAMTAYAR_LINK` edges to the existing destination. Both endpoints are filtered by active index in retrieval. It never deletes legacy nodes. Partial publications remain inactive. Destination and staging must be different instances; do not configure different DNS aliases for the same instance. Staging contains uploaded source-derived data and needs the same local care as your code.

CGC hardcodes Path.home() in this commit. Its child Python interpreter redirects that function to a per-attempt profile before importing upstream. This isolates global config/cache writes without changing upstream source or repurposing your system home. The configured executable must belong to a Python virtual environment containing CGC.

## First walkthrough

1. Open Settings, enter the two Neo4j connections and CGC path, save and test. Empty password inputs retain existing values. Secrets are stored in local `.env`, excluded from Git; this is single-user development storage, not an encrypted enterprise vault.
2. Upload a small ZIP with real functions/classes. Inspect accepted/excluded files.
3. Click Index. The real CGC process runs in the background. Follow the status and sanitized logs. No fabricated percentage is shown.
4. Wait for `ready`. Zero declarations is an error, not success.
5. Search an exact function name. Open source, then inspect its graph neighbors. Graph views cap results at 300 edges and show truncation.
6. Use Query templates for scoped statistics, symbol lookup or relationships.
7. Retrieve context using identifiers or filenames from your question. Export the JSON evidence pack.
8. Optionally set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY. Selected evidence is sent to that provider only when clicking the LLM action. No evidence means no model request.

Project IDs, archive hashes and index attempt IDs are separate. ZIP hashes are not Git commits. Reindexing creates a new active generation only after validation. All source evidence resolves against the retained immutable upload. Jobs interrupted by restart are marked interrupted; previous active indexes remain queryable.

## Validation

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

Browser smoke: install `playwright` in a disposable Node environment, install Chromium, start both services, then run `node tests/e2e/smoke.cjs` from HamtayarDemo. See docs/validation.md for checks actually executed in the implementation environment.

## API example

```powershell
$body = @{ question='process_order'; max_chars=16000 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/projects/PROJECT_ID/context' -ContentType 'application/json' -Body $body
```

API clients receive evidence independently of LLM generation. The endpoint is local and unauthenticated: do not expose the service to a network without an authentication/authorization layer.

## Current limits

This is an initial working application, not full CLI parity. There is no arbitrary Cypher execution, enterprise ACL, vector retrieval, live Git sync, watch mode, scoped deletion, MCP server, advanced call-path analysis, compiler-backed SCIP execution, report generator or bundle import. The capability inventory makes these limitations explicit. Graph layout is interactive; code viewing uses line numbers and selection highlighting rather than a full IDE. Retrieval is lexical and may need exact code identifiers for Persian questions. Large archives and graphs are intentionally capped. Upload validation/extraction is bounded but synchronous; indexing alone is queued. Failed publication data and staging generations require a future scoped retention implementation. Cancelling during publication prevents activation but may leave inactive rows.

Environment variables inherited by the server override .env during startup. Changing settings while indexing is blocked. Use one API process/worker; multiple uvicorn workers are not supported. Keep runtime/ on a durable local disk. All uploaded source and local .env must stay outside Git.
