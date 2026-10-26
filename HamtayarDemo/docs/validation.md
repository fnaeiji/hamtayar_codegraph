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
