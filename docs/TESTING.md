# Testing

| Command | Suite | Tooling |
|---|---|---|
| `make test-backend` | Unit, API and security tests | pytest 9, FastAPI `TestClient` |
| `make test-frontend` | Tree model and formatting unit tests | `node --test` (no extra dependency) |
| `make test-e2e` | Browser tests against a real server | Playwright for Python, Chromium |
| `make check` | Syntax check of every source file | `compileall`, `node --check` |

`make test` runs the first two. The e2e suite is opt-in (`-m e2e`) because it needs Chromium
(`backend/.venv/bin/playwright install chromium`) and the compiled CSS (`make css`).

## What each suite covers

**`tests/test_archive_security.py`** (malformed and hostile input): traversal in six forms
(`../`, nested `..`, backslashes, absolute, drive letters), symlinks, FIFOs, random bytes,
corrupted and truncated archives, empty upload, upload over the limit (service check,
`Content-Length` check and chunked streaming), file, entry and directory limits, depth,
oversized single files, total-size and compression-ratio bombs, lying size headers,
encrypted entries, duplicates, case collisions, file/folder conflicts, control characters,
non-flagged UTF-8 names, NFC normalisation, timeouts, file permissions, ZIP comments
containing fake signatures, ZIP64 archives, and temp-directory cleanup on success and failure.

**`tests/test_scanner.py`** (structure accuracy): ordering, nested counts, aggregate sizes,
duplicate basenames, files without extensions, hidden files, Unicode names, empty folders,
visible exclusions with entry counts, archive timestamps, disabling exclusions, `__MACOSX`,
empty archives, folder-only archives, implicit parent folders, stable ids, and symlinks not
followed when scanning a real directory.

**`tests/test_statistics.py`**: every statistic checked against a hand-counted fixture,
ordering of the largest files, `/stats` consistency, and the `.env` warning (asserting the
secret value never appears in the response).

**`tests/test_exclusions.py`** (Phase 2): `.gitignore` semantics (negation, folder-only,
anchored and nested files, deeper overriding shallower, no re-including inside an excluded
folder), rule order (include > custom exclude > defaults > `.gitignore`, `__MACOSX/` always),
toggles, pattern limits and comment handling. Through the API: excluded files and folders
listed with the exact rule; statistics excluding them; ignored folders not counting toward
`MAX_FILES`; an ignored `.env` never extracted; turning `.gitignore` off; custom patterns;
invalid patterns rejected before a job exists; oversized `.gitignore` reported; local-mode
scanning that reads `.gitignore` from disk.

**`tests/test_jobs.py`** (Phase 2): `202` response shape and completion; failures carried in
the job with cleanup; synchronous rejection of non-ZIP, corrupt and empty uploads; cancelling
running and queued jobs; the queue limit (`503`); cancelling a finished job as a no-op; crashes
becoming `internal_error` without leaking the message; timeouts inside a job; progress counts
always within their totals; unknown and malformed job ids; job-record expiry; shutdown
cancelling running work. Job tests replace the analysis with a controllable stand-in, so
cancellation is tested deterministically. All of them assert that the work directory is gone.

**`tests/test_generated.py`** (v0.3): a conventional `dist/` with bundles (high confidence);
a name alone (medium); a `build/` of real scripts *not* flagged (the v0.1 false positive);
ambiguous names that need a sibling manifest (`build.gradle`, `Cargo.toml`, `.csproj`), with
plain `target/` and `out/` not flagged; an unnamed folder of minified files; small or mixed
folders not flagged; excluded files not counted as evidence; generated counts in statistics.
A wrapper folder is not flagged because of its generated child: the first implementation got
this wrong, and these tests caught it.

**`tests/test_architecture.py`** (v0.4, 18 cases): parsers ignore look-alike imports in comments
and strings, count computed targets, handle TS type-only imports and re-exports, Python
relative levels and syntax errors, the size cap and cancellation (which exposed a tree-sitter
`ValueError` on cancel, now handled). Route and client URL detection, including ignoring
`client.get(...)` in tests. A realistic monorepo (React web app with tsconfig aliases,
workspace UI package, Express API with Prisma, Stripe, JWT and BullMQ): exact component set and
roles, evidence locations, workspace and alias resolution, the frontend → API HTTP link with
evidence on both sides, external services, frameworks, entry points, unresolved and dynamic
imports. A Python Flask/SQLAlchemy/Celery project with a `src/` layout (which exposed an
ancestor-folder resolver bug, now fixed). Turning code analysis off, projects without code,
generated and excluded files not parsed, the parse budget producing a partial map, and
endpoint validation.

Parser robustness (v0.4.1): hostile inputs at the size cap (extreme nesting, NUL bytes,
invalid UTF-8) on every language; the worker process kills a quadratic-time file at its time
limit and recovers, cancels mid-file, restarts after a crash, and cleans unencodable strings;
a hostile file inside a project does not stop the map.

**`tests/test_classifier.py`**: 33 classification cases, language detection, config labels.

**`tests/test_api.py`**: response shapes, tree depth, subtrees, reveal, search (partial,
case-insensitive, duplicate basenames, path queries, ancestors and pruning), extension,
classification and type filters, limits and truncation, validation errors, delete,
`server_busy`, JSON 404s, security headers, static frontend serving, store TTL and eviction.

**`frontend/tests/`**: `TreeModel` expansion, lazy versus non-lazy, ARIA set data, reveal,
depth-limited expand-all; formatting helpers.

**`tests/e2e/test_ui.py`**: upload → real statistics; expand, collapse and details; parent
navigation; excluded-folder details; keyboard navigation (arrows, Home/End, Left/Right);
search, empty results, classification and extension filters, and "show in full tree"; expand
and collapse all; overview links into the explorer; four upload-error cases (corrupt,
traversal, non-ZIP, too large); planned-feature pages; session restore and discard; no
horizontal scroll at 390 px. Phase 2 adds: `.gitignore` and custom rules entered in the UI and
shown in the overview, tree and details panel; options remembered across reloads; live job
progress with real counts on an 18,000-file archive, then cancel; and a running job resumed
after a page reload. v0.4 adds the architecture map: it renders with 10 nodes, the list view
and details work, an HTTP edge shows its evidence, and an evidence link opens the exact file in
the explorer (no console errors, which also guards the CSP). The main flows also fail on any browser console error. Screenshots go to
`backend/e2e-screenshots/`.

The tests were checked by mutation. Disabling the traversal, symlink or per-file-size guard
makes the security tests fail. Reversing `.gitignore` precedence, or making cancellation a
no-op, makes the Phase 2 tests fail.

## Fixture repository

`backend/tests/zip_factory.py` builds archives in memory. `SAMPLE_PROJECT` contains nested
folders, JS, TS, Python, CSS, SVG and CSV files, hidden files, files without extensions, a
Unicode name, duplicate basenames (`index.js` twice), an empty folder, config files,
`node_modules/` and `.git/`. `make sample` writes it to `samples/sample-project.zip` for manual use.

## Latest results (2026-11-03, v0.4.1)

```
backend:   248 passed (on both Python 3.11.16 and 3.14.6)
frontend:   14 passed
e2e:        20 passed (Chromium, headless; includes a 100,000-file upload and the architecture map)
```

CI runs the backend and frontend suites on Linux with Python 3.11 and 3.14, plus the browser
tests except the 100,000-file timing test, which is meaningful only on known hardware.

## Benchmarks

`backend/.venv/bin/python scripts/benchmark.py [counts…]` builds synthetic repositories
(50 packages × 400 modules × 7 sub-folders, 10 extensions, tiny files) and runs each size in
a fresh process: a full upload → job → result cycle, follow-up queries (best of 3), and a
second traced run that measures the memory one stored analysis retains.

Apple M4, 16 GB RAM, macOS (APFS SSD), Python 3.14.6, v0.3.0, 2026-10-24:

| Files | Archive | Nodes | Analyze total | Extract | Scan | Peak RSS | Retained / project | `/tree` depth 2 | Search (hit / miss) |
|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 0.2 MB | 2,452 | 0.41 s | 0.17 s | 0.05 s | 72 MB | 1.5 MB | 1.4 ms | 3.7 / 1.3 ms |
| 10,000 | 1.6 MB | 13,252 | 2.1 s | 1.1 s | 0.2 s | 92 MB | 8.4 MB | 1.5 ms | 10 / 2.2 ms |
| 20,000 | 3.3 MB | 23,252 | 3.8 s | 2.0 s | 0.3 s | 113 MB | 15.5 MB | 1.4 ms | 7.5 / 3.2 ms |
| 50,000 | 8.3 MB | 53,252 | 9.3 s | 5.2 s | 0.8 s | 181 MB | 35.5 MB | 1.4 ms | 9.8 / 5.4 ms |
| 100,000 | 16.6 MB | 103,252 | 17.9 s | 9.6 s | 1.4 s | 286 MB | 69.1 MB | 1.7 ms | 16.5 / 11.2 ms |

Peak RSS includes a Python/FastAPI baseline of 68–140 MB, which grows with the in-memory
test archive. "Analyze total" includes the upload, extraction, scanning, statistics,
generated-folder detection, deleting the extracted files, and job polling.

**In the browser** (`test_100k_file_project_stays_responsive`, headless Chromium, same
machine): with a 100,000-file project loaded, the explorer opens in about 60 ms, and a search
returns and renders in about 90 ms (excluding the 200 ms typing debounce). "Expand all"
switches to three levels, and fewer than 120 tree rows exist in the DOM.

### Architecture map cost (v0.4.0)

- Since v0.4.1 parsing runs in a worker process. Re-measured at 20k files: 4.22 s, so no
  measurable cost compared with in-process parsing (4.35 s). The other figures predate it.
- **Parser throughput on real code** (1,756 JS/TS/Python files, 20.5 MB, from installed
  packages): **~480 files/s, 5.6 MB/s** on one core. tree-sitter queries were measured as an
  alternative to the node walk and were not faster, because parsing itself dominates.
- **Synthetic benchmark with parsing on:** 20k files 4.35 s (was 4.0), 100k files 21.8 s (was
  17.9). Retained memory went from 0.67 to 0.75 KB per node.
- A real 100k-file repository with average-size files could need ~200 s of parsing. The
  `MAX_PARSE_SECONDS` budget (150 s) makes such maps partial (with a note) rather than failing
  the analysis.

### What the benchmarks changed (v0.3.0)

| Finding | Change |
|---|---|
| Stored analyses retained ~1.8 KB per node: 186 MB for one 100k-file project, ~1.9 GB worst case with 10 stored | Nodes are now slotted records (`services/nodes.py`), converted to Pydantic only for the slice a response returns: **~0.67 KB/node, 69 MB at 100k** (2.7× less). Peak RSS at 100k fell from 356 to 286 MB. |
| Memory scales with nodes, not projects | New `MAX_STORED_NODES` budget (500,000 ≈ 335 MB) evicts the oldest results first. The newest is always kept. |
| A full-depth `/tree` at 100k was 46 MB of JSON | `MAX_TREE_RESPONSE_NODES` (25,000) → `422 tree_too_large`. The UI never asks for more than 5,000. |
| Time is linear (~0.18 ms per file); 100k took 18 s | `MAX_FILES` raised **20,000 → 100,000** and `MAX_DIRECTORIES` 20,000 → 50,000. `MAX_ANALYSIS_SECONDS` 120 → 300 for slower hosts. `MAX_UNCOMPRESSED_BYTES` 500 MB → 1 GB. |
| Most of the time is filesystem work. At 50k files (profiled): extraction 4.6 s and deleting the extracted files 3.0 s, out of ~8.7 s | Not changed yet. See "Next" in IMPLEMENTATION_PLAN.md: measuring sizes by streaming decompression without writing files would remove both. |

Caveats: the synthetic files are tiny (a few bytes), so these numbers measure per-file
overhead. Repositories with large files add decompression and write time, bounded by
`MAX_UNCOMPRESSED_BYTES`. Slower disks, network filesystems and container overlay filesystems
can be several times slower; the 300 s budget allows for that. `MAX_ARCHIVE_ENTRIES` stays at
200,000, because `zipfile` keeps one ~0.5 KB record per entry while planning, excluded entries included.

## Not covered yet

- Cross-browser runs (Firefox, WebKit) and automated accessibility audits (axe).
- Windows hosts. The suite runs on macOS and Linux only.
- Load testing of concurrent uploads beyond the `server_busy` unit test.
