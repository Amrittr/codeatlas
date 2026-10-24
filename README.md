# CodeAtlas

**Understand any codebase. Visualize every connection.**

CodeAtlas is a codebase-intelligence platform for onboarding developers into unfamiliar
repositories. This first release (v0.1.0, Phase 1 MVP) securely analyzes a project ZIP
archive and visualizes its real file and folder structure. Analyses run as background jobs
with live progress, and what gets analyzed is controlled by `.gitignore` files and your own rules.

> Status: **v0.3.0**. Phase 1 MVP and Phase 2 (large repositories). Dependency graphs, architecture maps, GitHub import and the AI
> assistant are on the [roadmap](docs/IMPLEMENTATION_PLAN.md). The UI marks them as *Planned*.

## Features in this release

- **Secure ZIP analysis.** Path-traversal, symlink, decompression-bomb and size/count/depth
  protections are enforced during extraction. Nothing in the archive is executed. The only
  file contents read are `.gitignore` files, size-bounded, to decide what to skip. Details: [docs/SECURITY.md](docs/SECURITY.md).
- **Project overview.** File and folder counts, total size, extension distribution,
  classification breakdown (source, test, config, docs, …), detected languages, top-level
  structure, configuration files, largest files, excluded folders and warnings.
- **File explorer.** A virtualised, keyboard-accessible tree with lazy loading,
  expand/collapse all, server-side search (partial names or paths), filters by type,
  classification and extension, and a details panel for the selected file or folder.
- **Background analysis jobs.** The upload returns right away. Progress is shown with real
  counts ("4,797 of 18,000 files"), the analysis can be cancelled, and a reload resumes tracking.
- **Exclusion rules you can see.** Built-in rules skip dependency, VCS and cache folders.
  Every `.gitignore` in the archive is honoured with git's semantics (nested files, negation,
  folder-only and anchored patterns), and you can add your own exclude and always-include
  patterns. Excluded paths are not extracted and do not count toward limits, but they stay in
  the tree, each labelled with the exact rule that excluded it (for example
  `repo/.gitignore line 3: *.log`).
- **Generated-folder detection.** Build and generator output (`dist/` of hashed bundles,
  `target/` next to `Cargo.toml`, a folder of minified files) is recognised from file names and
  corroborating evidence, labelled with a confidence and the reason, and counted as Generated.
  It is still analyzed, not excluded.
- **Observed vs inferred.** Paths, sizes and counts are facts. Language and classification
  are inferences from names and extensions, shown with a confidence and a reason.

## Technology

| Layer | Choice |
|---|---|
| Backend | Python ≥ 3.11 (developed on 3.14), FastAPI, Uvicorn, Pydantic v2, `pathspec` (gitignore matching) |
| Frontend | Vanilla JavaScript ES modules, Tailwind CSS v4 (CLI build), no framework, no bundler |
| Storage | None. Results live in server memory with a TTL (see below) |
| Tests | pytest + FastAPI TestClient, `node --test`, Playwright (Chromium) |

## Prerequisites

- Python 3.11+
- Node.js 20+ (only to compile Tailwind CSS and run frontend unit tests)
- `make` (macOS and Linux include it; on Windows, run the commands from the Makefile by hand)

## Quick start

```bash
make setup      # venv + pinned Python deps, npm ci, build CSS
make dev        # http://localhost:8000
```

Open <http://localhost:8000> and drop a `.zip` of any project. To get demo archives:

```bash
make sample     # writes samples/sample-project.zip and samples/codeatlas-source.zip
```

GitHub's "Download ZIP" works directly. The single `repo-main/` wrapper folder is detected
and used as the project name.

### Manual setup (no make)

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm ci && npm run build:css)
(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000)
```

## Configuration

Copy `.env.example` to `.env` at the repository root. Every setting is optional and uses
the `CODEATLAS_` prefix. Upload limits, retention time, the temp directory, CORS origins and
whether the API also serves the frontend are all configurable. See
[`.env.example`](.env.example) for the full list and defaults.

The frontend reads its API base URL from `<meta name="codeatlas-api-base">` in
`frontend/public/index.html`. Leave it empty for the default single-origin setup.

## Testing

```bash
make test       # backend (pytest) + frontend unit tests (node --test)
make test-e2e   # Playwright browser tests; first run: backend/.venv/bin/playwright install chromium
make check      # syntax-check all Python and JS sources
```

See [docs/TESTING.md](docs/TESTING.md) for what each suite covers, and for benchmark results.

## Project layout

```
backend/        FastAPI app (app/) and tests (tests/, tests/e2e/)
frontend/       public/ is the deployable static site; src/input.css is the Tailwind source
docs/           product spec, architecture, API, security, testing, roadmap, changelog
scripts/        sample-archive generator and benchmark
```

## Current limitations

- Results are kept **in memory only** for 30 minutes by default (`CODEATLAS_PROJECT_TTL_SECONDS`)
  and are lost when the server restarts. There are no accounts and no persistence.
- There is no authentication. Anyone who can reach the server can upload, and anyone holding
  a project id can read that analysis. **Do not expose this release on a public network.**
- Jobs run in an in-process thread pool (2 at a time, 4 queued by default). Job and result
  state is lost on restart. Cancellation takes effect at the next checkpoint, typically within
  milliseconds.
- Default limits: 100 MB upload, 1 GB extracted, **100,000 analyzed files**, 50,000 folders,
  depth 64. Benchmarked at 100,000 files: about 18 s and under 300 MB peak memory on an Apple M4.
  See docs/TESTING.md for numbers and caveats. Excluded paths do not count toward the file limit.
- Changing exclusion rules means uploading again: the archive is deleted after each analysis.
- `.git/info/exclude` and global git excludes are not read. Only `.gitignore` files in the archive are.
- Classification and language detection use names and extensions only. Contents are not parsed.
- Only ZIP archives are supported (no tar, 7z or rar). No GitHub import yet.
