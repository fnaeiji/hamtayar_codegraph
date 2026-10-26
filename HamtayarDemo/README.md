# Hamtayar Code Intelligence

A local Persian/RTL React + FastAPI application for ZIP/RAR ingestion, CGC indexing, Neo4j graph exploration, source evidence, and optional OpenAI-compatible answers. Application code lives here; the upstream CGC checkout remains external.

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
2. Upload a small ZIP or RAR with real functions/classes. Inspect accepted/excluded files.
3. Click Index. The real CGC process runs in the background. Follow the status and sanitized logs. No fabricated percentage is shown.
4. Wait for `ready`. Zero declarations is an error, not success.
5. Search an exact function name. Open source, then inspect its graph neighbors. Graph views cap results at 300 edges and show truncation.
6. Use Query templates for scoped statistics, symbol lookup or relationships.
7. Retrieve context using identifiers or filenames from your question. Export the JSON evidence pack.
8. Optionally set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY. Selected evidence is sent to that provider only when clicking the LLM action. No evidence means no model request.

Project IDs, archive hashes and index attempt IDs are separate. Archive hashes are not Git commits. Reindexing creates a new active generation only after validation. All source evidence resolves against the retained immutable upload. Jobs interrupted by restart are marked interrupted; previous active indexes remain queryable.

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

This is an initial working application, not full CLI parity. There is no arbitrary Cypher execution, enterprise ACL, vector retrieval, live Git sync, watch mode, scoped deletion, MCP server, advanced call-path analysis, compiler-backed SCIP execution, report generator or bundle import. The capability inventory makes these limitations explicit. Graph layout is interactive; code viewing uses line numbers and selection highlighting rather than a full IDE. Retrieval is lexical and may need exact code identifiers for Persian questions. Large archives and graphs are intentionally capped. The UI streams uploads and queues extraction and indexing separately. The legacy multipart API remains synchronous for compatibility; large clients should use POST /api/projects/upload?filename=project.zip. Failed publication data and staging generations require a future scoped retention implementation. Cancelling during publication prevents activation but may leave inactive rows.

Environment variables inherited by the server override .env during startup. Changing settings while indexing is blocked. Use one API process/worker; multiple uvicorn workers are not supported. Keep runtime/ on a durable local disk. All uploaded source and local .env must stay outside Git.


## RAR upload

ZIP and RAR are detected from file contents, not just the filename. RAR3/RAR5 archives use `rarfile==4.5`; compressed entries need an external UnRAR or 7-Zip decoder. Stored RAR entries can be read without an external tool. Windows defaults are auto-discovered at `C:/Program Files/WinRAR/UnRAR.exe` and `C:/Program Files/7-Zip/7z.exe`.

If needed, install 7-Zip from https://www.7-zip.org/ or use your existing WinRAR installation. Set **RAR_7ZIP_TOOL** or **RAR_UNRAR_TOOL** in Settings using the full executable path. The app does not install an external program automatically. `GET /api/archives/capabilities` reports decoder readiness; the upload page shows an actionable notice when none is found. After changing the path, save Settings to refresh the status.

Update an existing installation:

```powershell
cd D:\CGC\HamtayarDemo
.\scripts\stop-dev.ps1
.\scripts\setup.ps1
.\scripts\start-dev.ps1
```

Only complete single-volume, unencrypted archives are supported. Password-protected archives, multipart sets, symlinks, hardlinks, redirected entries and special files are rejected. RAR extraction uses per-entry streams; external tools never extract archive paths onto disk themselves. Both ZIP and RAR use the same path checks, file-count/expanded-size limits, exclusion policy and actual decompressed byte limits. Extraction failure removes the partial workspace. After extraction both formats follow the same CGC indexing workflow.


## Large archives and connection resets

The UI sends raw archive bytes with transfer progress, then receives HTTP 202. Validation and extraction continue in the background; refresh/polling shows `archive_queued`, `extracting`, `ready_to_index` or `extraction_failed`. 100% upload means transfer completion, not completed extraction. Requests do not stay open throughout extraction. ZIP and RAR share this workflow. The existing multipart endpoint remains available for small/backward-compatible clients.

New defaults are 1024 MB upload, 8192 MB expanded data, 100000 archive entries and 25 MB per source file. **An existing .env is preserved by setup.ps1**, so explicitly update old MAX_UPLOAD_MB=50 / MAX_EXPANDED_MB=250 values if necessary:

```dotenv
MAX_UPLOAD_MB=1024
MAX_EXPANDED_MB=8192
MAX_ARCHIVE_FILES=100000
MAX_SOURCE_FILE_MB=25
```

Restart the backend after changing limits. Limits are finite and configurable, not a benchmark promise for arbitrary repository sizes. Available disk and RAM still constrain workloads. Remove dependency/build directories from archives when practical. Graph publication still has its documented 50000-node/100000-edge demo caps independently of archive upload limits.

Project polling returns at most 500 manifest entries and 200 log lines. The source explorer pages/filter files through GET /api/projects/{id}/files. Full metadata stays server-side. HTTP 413 reports the configured upload cap. Over-limit chunked transfers are stopped and their partial workspace is removed.

For ERR_CONNECTION_RESET first check `http://127.0.0.1:8000/api/health`. The Chrome extension resource warnings and React DevTools message are independent of API upload handling. The console alone cannot establish why the backend connection closed. Start scripts now capture runtime/backend.err.log, backend.out.log, frontend.err.log and frontend.out.log. Read backend.err.log for crashes or disk errors. Vite proxy and upload transfer timeouts are explicitly 30 minutes.

### Extraction budget and skipped files

The expanded-byte budget applies to selected entries, after excluding dependency/build directories (`node_modules`, `.git`, `.venv`, `vendor`, `dist`, `build`, `bin`, `obj`, `.vs`, `packages`), known binary/nested-archive extensions and files over MAX_SOURCE_FILE_MB. Every skipped file is listed with a reason; a skipped large source file is not analyzed. Actual bytes read remain bounded and checked against declared size. The archive entry-count limit still applies to all entries to bound metadata parsing.

If selected source still exceeds MAX_EXPANDED_MB, the error identifies the file, selected bytes and allowed bytes. Adjust the relevant setting and restart the backend, then click **تلاش مجدد استخراج** on the failed project. This reuses the retained archive. Startup logs show effective limits. A failed archive with no remaining readable source reports that explicitly.

### Indexing connection failures

Indexing requires both the isolated staging Neo4j (default Bolt 7689) and the destination Neo4j (default Bolt 7687). From `HamtayarDemo`, run `docker compose up -d staging` and `docker compose ps`. This compose file starts only staging; start your existing destination separately. Set both passwords in local `.env` or Settings. Changing the staging password in `.env` does not reset credentials in an existing Docker volume; use the existing password or reset it through Neo4j administration, without deleting data.

Use Settings → test destination and staging, or PowerShell:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/connection/test | ConvertTo-Json -Depth 5
```

Both results must report `ok: true`. The index job now tests both before launching CGC and logs the failed target with actionable, credential-free errors. Retry Start index on the existing project; re-uploading is unnecessary. Graph and context require a successfully published index. A successful connection test alone does not validate full indexing or destination write permissions.
