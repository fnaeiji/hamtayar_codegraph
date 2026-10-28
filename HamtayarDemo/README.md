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

New defaults are 1024 MB upload, 8192 MB expanded data, 250000 archive entries and 25 MB per source file. **An existing .env is preserved by setup.ps1**, so explicitly update old MAX_UPLOAD_MB=50 / MAX_EXPANDED_MB=250 values if necessary:

```dotenv
MAX_UPLOAD_MB=1024
MAX_EXPANDED_MB=8192
MAX_ARCHIVE_FILES=250000
MAX_SOURCE_FILE_MB=25
```

Restart the backend after changing limits. Limits are finite and configurable, not a benchmark promise for arbitrary repository sizes. Available disk and RAM still constrain workloads. Remove dependency/build directories from archives when practical. Graph publication has separate configurable ceilings; see the streamed publication section below.

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

Archive entry count includes directories and excluded dependency/build entries, to bound archive metadata processing. For example, an archive with 149,320 entries needs MAX_ARCHIVE_FILES=250000 in an existing local .env. Restart the backend, refresh the UI and use Retry extraction on the failed project; the retained archive is reused. Raising this limit does not change per-file, expanded-byte, or graph publication limits.


## Slow indexing diagnostics and explicit scope

The inspected CGC 0.6.13/pinned CLI reports missing files but then invokes a full discovery/pre-scan/parse/write/resolution pass. A count such as 10106/10224 is not remaining work or a completion percentage. The demo uses the same CGC indexing helper directly, bypassing the file-count-only early-success check which could skip unfinished relationship resolution. This remains a full selected-scope pass, not incremental resume. The child-process bridge uses CGC internal APIs; upstream files are untouched and incompatible versions fail visibly.

In Upload, use **بررسی فایل‌های سنگین و محدودهٔ ایندکس** before starting. It lists largest candidates and up to 100 exclusions. CGC language/ignore rules further narrow this selection. Use **گزارش زمان و فایل‌های کنارگذاشته‌شده** for actual selection counts, exclusions and slowest operations. Full reports are retained in `runtime/cgc/<job>/report.json`; API lists are bounded.

Settings exposes:
- `INDEX_MAX_FILE_MB=2`: exclude larger files before CGC pre-scan/parsing. Set `0` to disable this filter; extraction limits still apply.
- `INDEX_EXCLUDE_GLOBS=*.min.js,*.min.css,*.map`: comma-separated, case-insensitive filename patterns. Patterns containing `/` match relative paths. Set a single `-` to disable these exclusions.
- `INDEX_PARALLEL_WORKERS=2`: parsing concurrency, configurable 1..8.
- `INDEX_TIMEOUT_SECONDS=7200`: whole-process deadline, configurable 60..86400 seconds.

If your app ships third-party Stimulsoft bundles, optionally add `stimulsoft*.js` after reviewing the preview. Filenames alone do not prove the cause of a stall. Large first-party files may also be excluded by the size policy. Excluded files remain viewable as source but are not analyzed in the graph; context coverage discloses omissions. Publication filters old staging nodes against this attempt's selected paths so prior runs cannot reintroduce excluded files.

Logs include timestamps, CGC INFO diagnostics, and a heartbeat every 10 seconds with active stages/files and elapsed time. Parsing, pre-scan, writes and call-resolution timings are recorded. Heartbeat is process activity, not guaranteed progress. Buffered log updates avoid rewriting the large archive manifest for every line. Missing parsers and reported parse/write failures prevent publication. The former fixed publication limits are superseded by the streamed publication section below; large-project performance still depends on resources.

For an existing upload: cancel the active index, pull `codex/hamtayar-demo`, restart the demo, refresh the browser, review preview/settings, then start indexing on the same project. No re-upload is required. Changes affect the next attempt. Docker memory configuration remains separate.

## Streamed graph publication (replaces the fixed 50k/100k caps)

CGC completion and publication are separate stages. Publication now reads lazy Neo4j streams (fetch size 500) and writes bounded batches, instead of loading the whole graph and relationship list into Python. Driver connections are reused throughout the transfer. Destination lookup indexes on HamtayarEntity.id and .index are created before writing; the Neo4j user needs index creation permissions. Graph explorer caps are separate from stored graph size; see the dependency explorer section below.

Settings / local .env:

```dotenv
GRAPH_MAX_NODES=1000000
GRAPH_MAX_RELATIONSHIPS=5000000
GRAPH_PUBLISH_BATCH_SIZE=500
GRAPH_QUERY_TIMEOUT_SECONDS=1800
```

These are publication ceilings, independent of extraction and CGC scope. Above-limit output fails with the count/setting; it is never silently truncated or made active. The node ceiling includes shared pathless CGC entities. The relationship ceiling counts source relationships visited; canonical duplicate (source,target,kind) links collapse via MERGE, so final distinct relationship counts may be smaller. Approximate property-byte batching also flushes at 4 MiB; an individual larger property record still fits in its own batch. A streamed read has a finite query timeout and may require adjustment for very large transfers.

Use **تلاش مجدد انتشار گراف، بدون ایندکس مجدد** on a project whose CGC analysis completed but publication failed. The backend validates the completed report belongs to the uploaded workspace and reuses its selected scope. It creates a fresh destination generation and activates it only after successful publication. The old active generation remains usable on failure/cancellation. This also works with completed reports from before this change. Changing the analysis scope requires a new index, not a publication retry.

Progress logs report source node counts, transferred nodes and relationships. Failed partial generations remain inactive in Neo4j; this patch does not garbage-collect historical/partial generations. Publication cancellation is checked between records/batches; an in-flight database request must return or time out first. Keep staging unchanged during publication. All queries remain scoped to selected files/ancestors plus adjacent pathless entities, excluding other repositories' path-bearing nodes.

## Dependency explorer depth and class focus

From a symbol search result, click **گراف وابستگی این نود**. This opens the selected class/function as the graph root. The graph tab also offers a selector for the current symbol search results; text-search hits are not graph identities and must be opened through symbol search instead. Names may repeat across files: choose by kind/path/line. Entering the graph tab from the menu loads the current root, or a bounded project overview when no root is selected.

Select depth 1..5, direction (incoming, outgoing, both), actual project relationship kind and a node budget (100/200/500), then apply. The root has a gold border. Clicking another node selects it; **مرکز روی نود منتخب** or the expand button re-centers traversal at the selected depth. Original edge directions and kind labels remain visible. The graph response reports applied depth/direction, expanded depth and explicit truncation. It includes an isolated root even when no matching relationships exist.

Traversal is bounded breadth-first expansion, capped at 500 nodes and 1000 relationships with at most five hop queries. It does not enumerate unbounded variable-length paths. All visited endpoints belong to the project's active index. Overview has no root and is a bounded edge sample, not a multi-level class dependency tree. Large source/property blobs are omitted from graph responses.

These are stored static-analysis relationships, not newly inferred dependencies: a class may connect to its methods through CONTAINS/DEFINES and then to dependencies through CALLS, requiring depth 2 or 3 with all relationships enabled. A strict CALLS filter does not cross a structural class-to-method edge. Incoming/outgoing refer to the arrow of each selected relation, not a universal semantic definition of dependency. An empty filtered graph does not prove the class has no runtime dependencies. Existing published graphs work without re-indexing; missing CGC relationships cannot be manufactured by visualization.

## Readable graph canvas

Node names and relationship labels are hidden by default. Hover a node for its full name, kind, source path and direct relation count in the current view; its immediate neighborhood is highlighted while unrelated elements fade. Hover an edge for its kind and source → target names. Click a node to retain visual focus; clear focus or click the canvas background to reset it. These interactions do not discard graph data or trigger re-indexing.

The automatic layout uses breadth-first rings for a rooted neighborhood, ordering siblings together to reduce crossings, and a force layout for an unrooted overview. Placement is visual, not a new dependency/community inference. Nodes are smaller, edges thinner, and the root retains a gold border. Layout/fit/zoom controls, an expanded view (Escape to exit), an optional name-label toggle, and a keyboard-accessible node list are provided. Existing depth, direction and relation filters still control retrieval. The canvas displays the bounded API result, not the entire stored organizational graph.

Optional browser acceptance check: `node frontend/tests/graph-visual.cjs` from HamtayarDemo, with Playwright and a Chromium executable installed. `PLAYWRIGHT_MODULE` can point at an existing Playwright package and `GRAPH_TEST_BROWSER` at Chromium. `GRAPH_TEST_SCREENSHOT` optionally saves a viewport hover image and canvas image. The test starts a local Vite instance, mocks all application API responses with an 80-node fixture, and closes the server/browser afterward. It does not read or mutate Neo4j or real code repositories.
