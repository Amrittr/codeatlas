# Architecture

## Overview

```
Browser (frontend/public)                     FastAPI (backend/app)
──────────────────────────                    ─────────────────────────────────────────────
upload (XHR, real upload progress) ───────▶  POST /api/projects/analyze           (request thread)
                                               │ BodySizeLimitMiddleware (413 early)
                                               │ patterns validated (422), upload copied into a
                                               │ private work dir, archive_service.inspect_archive
                                               │ (magic, end record, entry count)
                                               ▼
                    ◀── 202 { job } ───────── JobManager.submit  (503 when slots + queue are full)
                                               ▼                                     (worker thread)
poll GET /api/jobs/{id} ◀── phase, counts ──  analysis_service.analyze_archive(…, AnalysisContext)
cancel DELETE /api/jobs/{id} ──────────────▶   ├─ archive_service.extract_archive   ← security boundary
                                               │     read .gitignore files (bounded) → ExclusionPolicy
                                               │     name normalisation, traversal → reject
                                               │     symlink/special/encrypted/collision → skip
                                               │     exclusion policy → not extracted, recorded
                                               │     limits, streaming extraction
                                               ├─ scan_service.scan_directory        (lstat only)
                                               │     excluded records injected as tree nodes
                                               │     analyzers: language, config, classifier
                                               ├─ statistics_service.compute_statistics
                                               ▼
                                             work dir deleted, then the job is marked final
                                             ProjectIndex  ──▶ ProjectStore (memory, TTL, LRU)
overview / explorer  ◀── JSON ──  GET /projects/{id} · /stats · /tree · /search
```

The scanner does not depend on how files arrived. ZIP import is one adapter. GitHub import
(Phase 3) and the local agent (Phase 9) will produce a directory or the same node schema and
reuse `scan_directory`, statistics and the index unchanged.

## Backend layout

| Module | Responsibility |
|---|---|
| `core/config.py` | All environment variables (`CODEATLAS_*`), read nowhere else |
| `core/errors.py` | `AppError(code, message, status)` and the JSON error handlers |
| `core/middleware.py` | Request-body size limit and security headers (CSP etc.) |
| `schemas/project.py` | The API data contract (Pydantic, camelCase JSON, `schemaVersion`) |
| `services/archive_service.py` | ZIP validation and safe extraction |
| `services/scan_service.py` | Filesystem walk, node construction, bottom-up aggregation |
| `services/statistics_service.py` | Project-level statistics derived from nodes |
| `services/project_index.py` | Read model: subtree slices (size-capped), reveal paths, search |
| `services/nodes.py` | Compact slotted node records, plus `to_api()` conversion at the response boundary |
| `services/analysis_service.py` | Pipeline orchestration, `AnalysisOptions`, warnings |
| `services/analysis_context.py` | Progress, cancellation and time budget shared by a job and the API |
| `services/job_service.py` | `JobManager`: bounded thread pool, queue limit, job records, work-dir ownership |
| `repositories/project_store.py` | In-memory TTL + LRU store |
| `analyzers/` | Language detection, config-file recognition, classification |
| `analyzers/generated_detector.py` | Evidence-based build-output folder detection |
| `analyzers/exclusions.py` | `ExclusionPolicy`: default rules, custom patterns and `.gitignore` semantics (via `pathspec`) |
| `api/routes/` | `health.py` (health, public config), `projects.py`, `jobs.py` |

Conventions: routes are thin; failures raise `AppError` with a stable `code`, never ad-hoc
responses. Analysis runs in the `JobManager` pool, never in a request. Request handlers do only
bounded work (copying the upload and reading the central directory).
New settings go in `core/config.py` and `.env.example`.

## Data model

Nodes are **normalised**: the index stores `id → node` and `id → ordered child ids`. Responses
are slices of that, never a nested copy of the whole tree.

- **Ids are stable**: `"root"` for the archive root, otherwise `n` + 16 hex digits of
  BLAKE2b over the relative path. Analyzing the same tree twice gives the same ids.
- **FileNode**: `id, name, path, parentId, depth, hidden, extension, sizeBytes, modifiedAt`
  (observed) and `language, classification, classificationConfidence, classificationReason`
  (inferred).
- **DirectoryNode**: `childCount, descendantFileCount, descendantDirectoryCount, sizeBytes`
  (aggregated), plus `excluded, excludedReason, excludedEntryCount` for excluded folders.
- Children are ordered folders first, then by natural case-folded name (`module2` before `module10`).
- In memory, nodes are slotted dataclasses (`FileRecord`, `DirectoryRecord`, about 0.67 KB each
  including index structures), not Pydantic models (about 1.8 KB). The Pydantic models in
  `schemas/project.py` stay the API contract. `to_api()` builds them with `model_construct` for
  just the nodes a response contains.
- Every response carries `schemaVersion` inside `project`, so clients can detect contract changes.

Relationship records (imports and so on) arrive in Phase 6 as separate normalised edge
records with `relationshipType`, `evidence {file, line}` and `confidence`.

## Frontend layout

```
frontend/public/
  index.html                 shell: sidebar nav, header, four <section data-view> regions
  js/app.js                  controller: upload flow, navigation, session restore, toasts
  js/api.js                  the only module that talks to the backend
  js/labels.js               display names and colours for schema enums
  js/components/treeModel.js pure tree state (unit-tested under Node)
  js/components/fileTree.js  virtualised ARIA tree (role=tree, aria-activedescendant)
  js/components/filterBar.js search + type/classification/extension filters
  js/components/detailsPanel.js
  js/views/overview.js | explorer.js | planned.js
  js/utils/dom.js            h() builder: text via text nodes only (no innerHTML anywhere)
```

- **No framework, no bundler.** Native ES modules load directly. Tailwind compiles
  `frontend/src/input.css` (theme tokens and a few component classes) to `public/assets/app.css`.
- **Tree scaling**: only rows in the viewport (plus overscan) exist in the DOM. Directories load
  their children on first expand (`/tree?nodeId=…&depth=1`). Search runs on the server and
  returns matches plus their ancestors as a pruned tree. The full tree's expansion state is
  kept while a search is active.
- **XSS**: every string from an archive is inserted with `textContent` and text nodes. Icons
  are built with `createElementNS`. The CSP forbids inline scripts and third-party origins.

## API boundary

The frontend uses only the documented endpoints in [API.md](API.md). The frontend and API can be
deployed separately: set `<meta name="codeatlas-api-base">` and `CODEATLAS_CORS_ORIGINS`,
and set `CODEATLAS_SERVE_FRONTEND=false` on the API.

## Security boundaries

See [SECURITY.md](SECURITY.md). In short: `archive_service` is the only code that touches
untrusted bytes. Everything after it sees validated names inside a private temp directory, and
nothing is ever executed.

## Background jobs

- `JobManager` owns a `ThreadPoolExecutor` with `MAX_CONCURRENT_ANALYSES` workers. It also
  enforces a queue limit: running plus queued jobs may not exceed workers + `MAX_QUEUED_JOBS`,
  otherwise `503 server_busy`.
- Each job owns a private work dir holding `upload.zip` and `project/`. It is removed when the
  job ends, whichever way it ends, and *before* the job reports a final state. A job that cannot
  be queued has its work dir removed by the request.
- `AnalysisContext.checkpoint()` runs between archive entries, extracted files (and 64 KB
  chunks) and scanned folders. It raises `AnalysisCancelled` after `DELETE /api/jobs/{id}` and
  `analysis_timeout` after `MAX_ANALYSIS_SECONDS` (measured from the job's start, not its queueing).
- Progress counts are written by the worker under a small lock and read by `GET /api/jobs/{id}`.
- On shutdown (FastAPI lifespan) every job is cancelled, and queued work dirs are removed.
- Threads rather than processes: the work is dominated by file I/O, which releases the GIL,
  and results must land in the in-process store. A separate worker process or queue (RQ,
  Celery, arq) becomes worthwhile with persistence or several API instances (Phase 10).

## Exclusion policy

`ExclusionPolicy.first_excluded(parts, is_dir)` checks each ancestor folder (cached), then the
entry itself. The first excluded component wins, and nothing beneath an excluded folder is
evaluated, as in git. Rule order: `__MACOSX/` → include patterns → exclude patterns → default
folder names → `.gitignore`. `.gitignore` evaluation walks the entry's ancestor folders shallow
to deep. In each one, `pathspec.GitIgnoreSpec.check_file` gives that file's verdict (last
match wins, `!` negates), and the deepest verdict wins. Every match carries a human-readable
`rule` (source file, line number, pattern).

The importer applies the policy **before extraction**, so excluded paths cost no disk I/O and
do not count toward `MAX_FILES`. It records each excluded folder (with an entry count) and
excluded file. The scanner injects those records into the tree with `excluded: true`. In local
mode, the scanner can instead apply a policy itself, reading `.gitignore` files as it walks.

## Generated-folder detection

`detect_generated_folders` runs after scanning. Bottom-up, each folder gets its analyzed
descendant count and how many of those have artifact-like names (`classifier.artifact_reason`:
minified, source map, hashed bundle with a letters-and-digits token, compiled extension,
code-generator suffix). The rules:

| Evidence | Verdict |
|---|---|
| Conventional output name (`dist`, `coverage`, `.next`, …) or a corroborated ambiguous name (`build/` + `build.gradle`, `target/` + `Cargo.toml`/`pom.xml`, `bin/` + `*.csproj`), with ≥ 50% artifacts | high |
| The same names alone | medium |
| Ambiguous name without a marker, with ≥ 30% artifacts | medium |
| Any folder whose *own* files (not those explained by a qualifying subfolder) are ≥ 80% artifacts (≥ 3 files) / ≥ 50% (≥ 5 files) | high / medium |

The shallowest qualifying folder is reported, and its files are reclassified. Folders are
never excluded by detection.

## Decisions

| Decision | Why |
|---|---|
| Extract to disk, then scan, rather than reading only the ZIP index | Sizes come from real decompressed bytes, not untrusted headers. The scanner stays shared with future local and GitHub modes. Later parsing phases need the files. |
| In-memory store with project ids (not stateless responses) | Enables lazy tree loading and server-side search. No database until accounts or persistence need one (Phase 10). |
| Our own case-insensitive collision detection | Same result on Linux and macOS. Never silently merges `Src/` and `src/`. |
| Traversal and absolute paths reject the **whole** archive; symlinks and odd entries are skipped | A traversal entry signals a hostile archive. Symlinks are common in real repos. |
| Build-output folders (`dist`, `build`, `target`) are not excluded | They sometimes hold meaningful committed files, so they are classified `generated` instead. |
| Tailwind CLI via npm (pinned) | Real production build with no runtime CDN, and the CSP stays `'self'`-only. |
| `node --test` for frontend unit tests | No added test dependency. Playwright covers browser behaviour. |
| `pathspec` for gitignore matching | git's semantics (anchoring, `**`, folder-only, negation, escapes) are easy to get subtly wrong. `pathspec` is pure Python, has no dependencies, and reports which pattern matched. |
| Upload checks synchronous, analysis asynchronous | Bad files fail instantly with a normal HTTP error. Only real work goes to the queue. |
| Excluded files have `sizeBytes: null` | They are never extracted, and sizes in the ZIP header are not trusted. |
| Generated folders are labelled, not excluded | Spec: never silently drop meaningful files. Names are evidence, not proof. |
| Slotted records internally, Pydantic at the boundary | Measured 2.7× less retained memory, with no change to the API contract. |
| Memory budget in nodes, not projects | Retained memory is proportional to nodes. 10 small projects and 1 huge one cost very different amounts. |
| Statistics count analyzed paths only | Excluded counts are reported separately (`excluded*`), so totals mean "what CodeAtlas looked at". |

## Extension points

- **New import source**: produce a directory (or node list) and call the scan/statistics/index
  pipeline. Add a route that reuses `ProjectStore`.
- **New language or config rule**: add entries to `analyzers/language_detector.py` or
  `config_detector.py`. Classification rules live in `analyzers/classifier.py`, with tests in
  `tests/test_classifier.py`.
- **Parser adapters (Phase 5)**: `analyzers/parsers/<language>.py` exposing a common interface,
  producing symbol and relationship records keyed by node id.
- **Out-of-process workers**: `JobManager` exposes `submit`, `get`, `cancel` and `shutdown`. A
  Redis or Postgres-backed implementation can replace it without touching routes or the pipeline.
