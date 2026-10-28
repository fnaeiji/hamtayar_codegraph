# Validation record

Executed in the Linux implementation workspace:
- Backend archive/API/scoping/publication-boundary tests: 12 passed.
- TypeScript noEmit check and Vite production build: passed.
- Backend and frontend development servers: started successfully.

Not yet claimed:
- Real CGC indexing through staging and destination Neo4j: this workspace has no Docker daemon or access to the user's Windows CGC installation/database.
- Windows PowerShell process-control scripts: source-reviewed, not executed on Windows.
- Real LLM provider: requires user configuration.

Unit tests use graph-boundary doubles where Neo4j is required. They are not a substitute for the real graph acceptance flow. Run scripts/smoke-test.ps1 and the README walkthrough on the user's Windows machine before treating the demo as validated end to end.

Browser smoke execution was attempted, but Chromium was unavailable and its download returned an invalid archive in this environment. The smoke script is provided; no browser pass or visual verification is claimed.


## RAR update

- 28 backend tests passed after adding RAR, including a genuine stored RAR3 upload/source-read round trip, a genuine compressed RAR5 fixture with missing-decoder handling, malformed signatures, rejected links/redirects/volumes/passwords, and actual-vs-declared size checks.
- Frontend TypeScript/build verification is recorded with the change.
- This environment has no UnRAR/7-Zip binary: successful compressed RAR decompression on Windows remains a local acceptance check, not a claimed test pass. End-to-end CGC/Neo4j limitations above remain unchanged.
- Small third-party binary fixtures are represented as base64, with provenance and ISC notice in backend/tests/fixtures/LICENSE.rarfile.


## Large upload update

- 35 backend tests passed: streamed upload acceptance, background extraction, HTTP 413 including missing Content-Length, failed-extraction state, cancellation and manifest pagination, plus earlier tests.
- TypeScript/build passed.
- An actual 64 MiB ZIP was streamed via the running Vite proxy into FastAPI, returned HTTP 202, and completed background extraction of 8 source files while health checks stayed responsive. This verifies transport/extraction only, not CGC indexing of a large codebase.
- No claim is made that the user's exact Windows connection reset was reproduced; its backend logs are not available here.

## Extraction policy correction

38 backend tests passed, including excluded oversized dependencies not consuming the selected-source budget, oversized individual source skipped without opening, actionable aggregate-limit errors before extraction, and retry using the stored archive. TypeScript/build verified. This change does not assert that the user's unseen archive has been tested.

## Slow indexing and timeout diagnostics

- 52 backend tests passed; frontend TypeScript and production build passed.
- The optional bridge integration test ran with installed CGC 0.6.13, real discovery/pre-scan/C# parsing and resolution using the installed native C# grammar. Database persistence was mocked. A second run with an unavailable parser correctly failed instead of publishing an incomplete graph.
- Tests cover explicit size/pattern exclusions without source deletion, disabling policy filters, invalid limit values, active/slow operation tracking, bounded report responses and publication query scoping to selected paths.
- No Docker daemon is available in this environment. The user's 10,224-file archive, Windows cancellation and full CGC-to-staging-to-destination publication were not exercised here. No measured speedup or full large-project completion is claimed.
- Existing graph publication limits remain 50,000 nodes / 100,000 edges. The new 7,200-second default CGC deadline is configurable, and increasing it alone is not a performance fix.

## Streamed publication update (supersedes fixed 50k/100k limits)

- 60 backend tests passed; 2 optional CGC analysis bridge tests skipped because the CGC package was not installed for this run. Frontend TypeScript and production build passed.
- Lazy-source/destination stand-in regression: 50,501 nodes and 100,501 distinct canonical relationships published in batches of at most 500. Tests cover empty graph vs count limits, shared entities counting toward caps, cancellation/connection closure, selected-path query boundaries, publication-only retry, report ownership, and preservation of the previous active index on failure.
- A separate live test ran TWO isolated Neo4j Community 5.26.0 servers with 512 MiB heaps using Java 17 in this environment. Seeded 50,501 Function nodes, 100,501 physical CALLS relationships, one adjacent pathless Module with two edges and one adjacent foreign-repository Function. Real publication completed in 16.03 seconds with 50,502 destination nodes and 50,503 distinct canonical relationships. Parallel CALLS collapse under the pre-existing (source,target,kind) MERGE semantics. The foreign node was absent from the destination. Both test servers were shut down afterward.
- This live test exercises real Cypher, driver streaming, index creation, node/edge writes and scoped readback. It does not run CGC analysis of the user's archive, Windows Docker, or establish a production throughput guarantee. The user's exact graph count is not known from the old combined-limit error.
- The uploaded log shows successful CGC completion after 769.0 seconds followed by publication failure; retrying publication can reuse that completed report without repeating analysis.

## Multi-level dependency explorer

- 71 backend tests passed (2 optional CGC bridge tests skipped); TypeScript/build passed. Unit/API tests cover bounded depth, direction, cycles, isolated/filtered roots, stale or foreign identities, explicit truncation, and parameter validation.
- A real Neo4j Community 5.26.0 test created a small class/method/dependency graph with a cycle, isolated class and adjacent foreign-index node. Verified exact outgoing neighborhoods at depth 1/2/3, incoming arrows, filtered roots, node-budget truncation, dynamic relationship kinds and rejection of a foreign root. Test data and the isolated test server were cleaned up.
- This verifies retrieval over stored relationships, not completeness of CGC's dependency extraction for the user's class. The user's exact class name/source and graph were not supplied.
- The real Neo4j test also passed after anchoring each hop at indexed frontier identities instead of scanning all project relationships. Browser interaction testing was unavailable because Chromium download returned an invalid/truncated archive; no browser-render or click-through pass is claimed.
