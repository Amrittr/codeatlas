# Changelog

## 0.3.0 — 2026-10-24 — Phase 2 complete

### Added
- **Generated-folder detection** (`analyzers/generated_detector.py`). It uses evidence from file
  names (minified, source maps, hashed bundles, compiled and code-generator output), conventional
  output names and sibling manifests (`build/` + `build.gradle`, `target/` + `Cargo.toml`/`pom.xml`,
  `bin/` + `.csproj`). Folders get `generated`, `generatedConfidence` and `generatedReason`, and
  their files are reclassified. Stats gain `generatedFolders` and `generatedFolderCount`. In the
  UI: a "Likely generated folders" card, a tree badge, and a details banner.
- File-level classification recognises hashed bundles (`main.3f9a2c1b.js`, `index-BK3j8d_a.js`)
  and code-generator output (`_pb2.py`, `.pb.go`, `.generated.ts`, …).
- `scripts/benchmark.py` runs 1k–100k files, one process per size, and reports retained memory.
- A 100,000-file browser test (`test_100k_file_project_stays_responsive`).
- `MAX_STORED_NODES` (500,000) memory budget for stored results, and `MAX_TREE_RESPONSE_NODES`
  (25,000) with `422 tree_too_large`.

### Changed
- **Limits raised from benchmark results:** `MAX_FILES` 20,000 → 100,000, `MAX_DIRECTORIES`
  20,000 → 50,000, `MAX_UNCOMPRESSED_BYTES` 500 MB → 1 GB, `MAX_ANALYSIS_SECONDS` 120 → 300.
- Nodes are stored as slotted records. Retained memory went from ~1.8 KB to ~0.67 KB per node
  (69 MB for a 100k-file project), and peak RSS at 100k from 356 MB to 286 MB.
- Folder names alone no longer make files "generated": a `build/` folder of scripts keeps its
  real classification (a false positive in v0.1–v0.2).
- Tree children use natural order (`module2` before `module10`).
- `schemaVersion` is `"3"` (new fields only; nothing removed).

## 0.2.0 — 2026-10-24 — Phase 2, part 1

### Added
- **Background analysis jobs.** `POST /api/projects/analyze` now returns `202 { job }` after
  saving the upload and running the cheap structural checks. New endpoints:
  `GET /api/jobs/{id}` (status, phase, real progress counts, `projectId` or `error`) and
  `DELETE /api/jobs/{id}` (cancel). Bounded worker pool and queue (`MAX_QUEUED_JOBS`,
  `JOB_TTL_SECONDS`). Work directories are removed on every outcome and on shutdown.
- **`.gitignore` support** with git's semantics, through `pathspec` 1.1.1. Nested files,
  negation, folder-only and anchored patterns all work. Can be switched off per upload.
- **Custom exclusion rules**: `excludePatterns` and `includePatterns` (gitignore syntax) per upload.
- Exclusions are applied **before extraction**: excluded paths are not written to disk and do
  not count toward `MAX_FILES`. Excluded files and folders stay in the tree with
  `excluded`, `excludedReason` and `excludedRule` (for example `repo/.gitignore line 3: *.log`).
- UI: "What to leave out" options (remembered per browser), live job progress with real
  counts, cancel during upload or analysis, resume tracking after a reload, an "Excluded paths"
  overview card, excluded rows and rule details in the explorer.
- Tests: `test_exclusions.py`, `test_jobs.py` and three new e2e flows (168 / 14 / 16 passing).

### Changed (breaking for API clients)
- `schemaVersion` is now `"2"`. `project.defaultExclusionsApplied` is replaced by
  `project.exclusionSettings`. `stats.totalDirectories` and all other statistics now count
  analyzed paths only; new `excludedFileCount`, `excludedDirectoryCount` and
  `excludedEntryCount`. `exclusions[]` gains `type` and `rule`, plus a top-level
  `exclusionCount`. `FileNode.sizeBytes` is `null` for excluded files. The warning
  `directories_excluded` is renamed `paths_excluded`; `gitignore_not_applied` is new.
- `server_busy` now means "workers and queue full" rather than "one analysis running".

## 0.1.0 — 2026-10-24 — Phase 1 MVP

### Added
- FastAPI backend: `GET /api/health`, `GET /api/config`, `POST /api/projects/analyze`,
  `GET|DELETE /api/projects/{id}`, `/stats`, `/tree` (lazy, depth, reveal), `/search`.
- Secure ZIP import: own end-of-central-directory parsing and entry counting; traversal
  rejection; skips for symlinks, special files, encrypted entries, duplicates, case
  collisions and unsafe names; streaming limits on per-file size, total size, compression
  ratio, file, folder and entry counts, depth and time; `O_EXCL|O_NOFOLLOW` file creation;
  guaranteed temp cleanup.
- Filesystem scanner with stable path-based ids, folders-first ordering and bottom-up
  aggregates. Language detection, config-file recognition and classification with
  confidence and reason.
- Default exclusions (dependencies, VCS, virtualenvs, caches), shown in the tree with entry
  counts and switchable per upload.
- In-memory project store with TTL and LRU eviction.
- Security headers with a strict CSP. Request-body size limit middleware. Concurrency limit.
- Dark dashboard UI (vanilla ES modules + Tailwind v4): upload with drag and drop and real
  upload progress; overview of statistics, distributions, structure, config files,
  exclusions, largest files and skipped entries; virtualised ARIA tree with lazy loading,
  keyboard navigation, server-side search and filters, and a details panel; planned features
  clearly marked; session restore; discard.
- Test suites: 138 backend, 14 frontend unit, 13 Playwright e2e. Benchmark script.
- Docs: README, product spec, architecture, API, security, testing, implementation plan.
