# Implementation Plan

Each phase leaves the product usable and tested. A phase is complete only when its criteria
have been **verified**, not just implemented.

| Phase | Name | Status | Depends on |
|---|---|---|---|
| 0 | Repository inspection & setup | ✅ Done | — |
| 1 | Functional MVP (ZIP → tree + stats) | ✅ Done (v0.1.0) | 0 |
| 2 | Robust scanning & large repositories | ✅ Done (v0.2.0–v0.3.0) | 1 |
| 3 | GitHub integration | Planned | 2 |
| 4 | Project overview & configuration intelligence | 🟡 Partly done in v0.4 (frameworks, manifests, entry points) | 1 |
| 5 | Code parsing & symbol indexing | 🟡 Partly done in v0.4 (imports, routes for JS/TS/Python; no symbols yet) | 2, 4 |
| 6 | Dependency graph | 🟡 Component-level in v0.4; file-level graph view planned | 5 |
| 7 | Architecture visualisation | ✅ v1 in v0.4 (generated map, evidence, confidence) | 4, 6 |
| 8 | AI codebase assistant | Planned | 5, 6 (7 helps) |
| 9 | Local analysis agent | Planned | 2 |
| 10 | Teams & enterprise readiness | Planned | 3, 9 |

## Phase 0 — Inspection and setup ✅

The working directory was empty, so there was no existing code to keep or migrate. Done:
stack chosen per the spec (FastAPI + vanilla ES modules + Tailwind), repository layout,
pinned dependencies, Makefile, docs. Decisions confirmed with the product owner: npm Tailwind
CLI build; in-memory results with project ids and TTL; moderate default limits; Playwright e2e.

## Phase 1 — Functional MVP ✅

| Criterion | Verified by |
|---|---|
| App starts | `make dev`; e2e suite starts a real uvicorn |
| Frontend talks to backend | e2e uploads through the UI |
| Real ZIP → correct tree | `test_scanner.py`, e2e expand/collapse |
| Statistics match the project | `test_statistics.py` (hand-counted fixture), e2e |
| Search and filters work | `test_api.py`, e2e search/filter test |
| Security validation passes | `test_archive_security.py` (45 cases, mutation-checked) |
| Automated tests pass | 138 backend + 14 frontend + 13 e2e |
| Clean-environment setup | `make setup` steps in the README |
| Limitations documented | README "Current limitations", SECURITY.md |

## Phase 2 — Robust scanning and large repositories ✅

| Item | Status | Verified by |
|---|---|---|
| Background jobs: `202` + job id, phases with real counts, cancellation at checkpoints, queue limit, cleanup on every path, resume after reload | ✅ v0.2.0 | `test_jobs.py` (14 cases), e2e progress/cancel/resume |
| `.gitignore` support (nested, negation, folder-only, anchored), applied before extraction | ✅ v0.2.0 | `test_exclusions.py`, e2e |
| Configurable exclusions: toggles plus custom exclude and always-include patterns, per upload | ✅ v0.2.0 | `test_exclusions.py`, e2e |
| Exclusions visible with the exact rule (tree, details, overview), statistics on analyzed paths only | ✅ v0.2.0 | API and e2e tests |
| Excluded paths do not count toward `MAX_FILES` | ✅ v0.2.0 | `test_ignored_files_do_not_count_toward_file_limit` |
| Generated-folder detection from evidence: artifact share, conventional names, sibling manifests | ✅ v0.3.0 | `test_generated.py` (8), e2e, no false positives on the CodeAtlas repo |
| Benchmarks at 1k–100k files; limits raised to 100k files / 50k folders / 1 GB / 300 s | ✅ v0.3.0 | `scripts/benchmark.py`, TESTING.md |
| Leaner node storage (0.67 KB/node, was 1.8), store node budget, capped tree responses | ✅ v0.3.0 | benchmark, `test_api.py` |
| UI responsive at 100k files (explorer ~60 ms, search ~90 ms, < 120 DOM rows) | ✅ v0.3.0 | `test_100k_file_project_stays_responsive` |
| Measure sizes by streaming decompression instead of writing files (would remove most of the file-creation and deletion time, and keep source off disk) | ⏭ Next | |
| Paginated search and virtualised results above 2,000 matches | Planned | |
| Synthetic 1k–100k benchmark suite in CI with recorded hardware | Planned | |

Completion criteria met: large projects are scanned within documented, measured limits;
the interface stays responsive (measured at 100k files); limits are enforced; exclusions are
visible; performance tests set the limits. 100,000 files is the tested ceiling, not a claim
about larger repositories.

## Phase 3 — GitHub integration

GitHub App (least privilege, read-only contents) → repo and branch selection → tarball
download for a specific commit SHA → the same extraction safety and scan pipeline. Rate-limit
and auth-error handling. Credentials stay server-side. Needs persistent sessions, so this is
where PostgreSQL or another store is introduced.

## Architecture map v1 (v0.4.0), a vertical slice through Phases 4–7

Requested so that a project with no architecture diagram gets one generated. Built as one slice
rather than strictly phase by phase, with these decisions from the product owner: map now and
deepen later; JS/TS + Python first; real parsers (tree-sitter, `ast`); an interactive map in the app.

| Delivered | Verified by |
|---|---|
| Manifest reading: package.json, pyproject, requirements, tsconfig/jsconfig paths, entry points | `test_architecture.py` |
| Import extraction (tree-sitter JS/TS/TSX, Python `ast`), route and URL extraction, browser-API detection | parser tests |
| Resolution: relative paths, aliases, workspaces, Python packages and `src/` layouts, built-ins | monorepo and Python fixtures |
| Components, roles with evidence and confidence, connections, HTTP links, external services | fixture assertions; CodeAtlas's own repo |
| Interactive Cytoscape map, list view, evidence links into the explorer | e2e `test_architecture_map` |
| Parse budget with partial maps; option to turn code analysis off | tests |

**Next for the map:** more languages (Java, Go, C#) through new parser adapters; symbol
indexing (functions and classes with lines, Phase 5); a file-level dependency graph view with
neighbourhood exploration (Phase 6); route-to-handler linking; detecting existing architecture
docs and diagrams in the repo; exporting the map (SVG/PNG, Mermaid).

## Phase 4 — Configuration intelligence

Extend `analyzers/config_detector.py` into rules that read manifests safely (parsing
`package.json`, `pyproject.toml` and similar as data, never executing them). Detect
frameworks, build systems, package managers, test frameworks and likely entry points, each
with evidence (file + key) and a confidence. Unknown project types stay fully usable.

## Phase 5 — Parsing and symbol indexing

Language adapters (tree-sitter is the likely choice for JS/TS/Python/Java). Symbols with
path and line ranges. A parse failure marks that file and never fails the analysis.

## Phase 6 — Dependency graph

Import and export edges with evidence and confidence. Cytoscape.js with neighbourhood
expansion, filters, legend, and navigation back to the tree. No inferred edges without evidence.

## Phase 7 — Architecture map

Candidate modules from imports, conventions and configuration, labelled as hypotheses when
uncertain. Navigation: overview → architecture → module → tree → graph.

## Phase 8 — AI assistant

Retrieval over symbols, configuration and edges. Answers cite paths and line ranges, and
say when evidence is missing. Guards against prompt injection from repository content. Cost
and context limits. Code is sent to an AI provider only with explicit consent, documented
per processing mode.

## Phase 9 — Local agent

A local scanner that reuses `scan_directory`, restricted to the folder the user picks. It
emits the same schema and makes no silent uploads.

## Phase 10 — Teams and enterprise

Accounts, organisations, RBAC, persistent projects, history and diffs, audit logs, retention
policies, monitoring. Requires a security review before any "enterprise-ready" claim.

## Phase 1 development checklist

- [x] Health endpoint, public config endpoint
- [x] ZIP upload with size limits (middleware and service)
- [x] Archive validation, secure extraction, cleanup
- [x] Recursive scan, metadata, classification, statistics
- [x] Tree, stats, search, delete endpoints with validation and JSON errors
- [x] Dashboard, drag-and-drop upload with real upload progress, honest processing state
- [x] Virtualised tree, expand/collapse (all), search, filters, details panel
- [x] Error, empty and loading states; responsive layout; keyboard navigation
- [x] Unit, API, security and browser tests; benchmarks
- [x] Documentation set
