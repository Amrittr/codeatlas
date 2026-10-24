# Security

CodeAtlas may process confidential source code. Every uploaded archive is treated as hostile.

## Upload and ZIP safety

Controls live in `backend/app/services/archive_service.py` and `backend/app/core/middleware.py`.
Each has a test in `backend/tests/test_archive_security.py`.

| Threat | Control |
|---|---|
| Oversized upload | `Content-Length` checked before the body is read. Streamed bytes are counted for chunked uploads → `413`. The service checks the size again. |
| Non-ZIP or malformed file | Magic-byte check (`415`). The end-of-central-directory record is parsed by our own code, and `zipfile` errors become `400 invalid_archive`. |
| Huge central directory (memory DoS) | Central-directory headers are counted by walking them **before** `zipfile` parses the archive. Over `MAX_ARCHIVE_ENTRIES` → `413`. The declared count is not trusted. |
| Path traversal / ZIP slip | Names are normalised (`\` → `/`, NFC). Any `..` component, leading `/` or drive letter **rejects the whole archive** (`400 unsafe_archive`) before anything is written. A per-directory `realpath` check confirms containment as defence in depth. |
| Symlinks, device files, FIFOs | Never created. Listed as skipped (`symlink_not_followed`, `special_file`). |
| Decompression bombs | Extraction streams 64 KB chunks and counts **actual** output bytes against the per-file limit (file skipped), the total uncompressed limit (`413`) and a whole-archive compression-ratio limit above 10 MB (`413`). Declared sizes are used only to fail fast. |
| Lying size headers | `zipfile` stops at the declared size and the CRC check fails, so the entry is skipped as `corrupt_entry`. It cannot write more than declared. |
| Excessive files, folders or nesting | `MAX_FILES` (excluded folders do not count), `MAX_DIRECTORIES` and `MAX_DEPTH` are checked before extraction and again in the scanner. |
| Overwrites and merges | Planned paths are tracked case-insensitively. Duplicates, case collisions and file/folder conflicts are skipped and reported. Files are opened with `O_CREAT|O_EXCL|O_NOFOLLOW`. |
| Encrypted entries | Skipped. Nothing ever asks for a password. |
| Slow archives | Every phase checks `MAX_ANALYSIS_SECONDS` → the job fails with `analysis_timeout` (408). |
| Concurrent load | At most `MAX_CONCURRENT_ANALYSES` jobs run and `MAX_QUEUED_JOBS` wait. Beyond that → `503 server_busy`, and the upload is deleted at once. |
| Hostile `.gitignore` files | Only regular, unencrypted entries named exactly `.gitignore` are read, through the same normalised-name checks. Each is capped at 256 KB (read with a bounded `read`, so the declared size is not trusted) and at most 500 are applied. Content is decoded as UTF-8 with replacement and used only as patterns, never executed. Oversize or unreadable files are reported as `gitignore_not_applied`. |
| Hostile custom patterns | At most 100 patterns of 256 characters per field (8 KB form limit). Rejected with `422` before any work starts. |
| Control characters in names | Entry skipped (`unsafe_name`). Names in error output are sanitised. |

Extracted files are created with mode `0600` inside a `0700` directory made by
`tempfile.mkdtemp`. Executable bits from the archive are not preserved.

## Source-code handling

- Uploaded code is **never executed**. Dependencies are never installed and no scripts run.
- The scanner calls `lstat` only. **File contents are not read**, with one exception:
  `.gitignore` files, which decide what is excluded. Classification uses names.
- Paths excluded by any rule are **never extracted**. Excluded `.env` files therefore never
  touch the disk.
- The upload is copied into a private per-job work directory (`0700`, archive `0600`). The job
  owns it and deletes it, archive and extracted files together, when it completes, fails or is
  cancelled, and before it reports its final state. Uploads rejected by the synchronous checks,
  or by a full queue, are deleted inside the request. Tests assert that nothing is left behind
  in every one of these paths, including server shutdown.
- Starlette spools multipart uploads larger than 1 MB to the OS temp directory while the request
  is processed. That spool file is deleted when the request ends.
- Job records (status, progress counts, error code, file name) are kept in memory for
  `JOB_TTL_SECONDS` (default 10 min) after a job finishes. They contain no file paths or contents.
- What remains is **metadata only** (names, paths, sizes, timestamps, classifications), held in
  process memory for `PROJECT_TTL_SECONDS` (default 30 min), up to `MAX_STORED_PROJECTS`
  (default 10) and `MAX_STORED_NODES` (default 500,000 nodes, about 335 MB), oldest evicted first. `DELETE /api/projects/{id}` (the **Discard** button) removes
  it at once. Restarting the server clears everything.
- `.env` files are recognised by name and trigger a warning. Their contents are never read.
- The browser remembers the exclusion options (checkboxes and patterns) in its own
  `localStorage`, and the id of a running job in `sessionStorage`. Neither contains file contents.

## Logging and errors

- Logs record project ids, counts and durations. File names and contents are not logged.
- `500` responses carry a generic message. In production, tracebacks are not logged either,
  because they could quote archive paths.
- No secrets exist in this release. Future credentials (GitHub app keys, AI provider keys)
  belong in environment variables only, and are never sent to the browser.

## HTTP hardening

All responses get `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and
`X-Frame-Options: DENY`. They also get a strict CSP: `default-src 'self'`, no inline
scripts, no third-party origins, `frame-ancestors 'none'`. The frontend builds DOM nodes with
text nodes only (no `innerHTML`), so file names cannot inject markup. Swagger UI at `/api/docs`
(development only) is exempt from the CSP because it loads from a CDN.

## Access control: known limitation

**There is no authentication in v0.2.** Project and job ids are random 128-bit values and work like
bearer tokens: anyone who holds an id can read that analysis until it expires. Anyone who can
reach the server can upload. Run it on `localhost` or a trusted network only. Accounts and
role-based access are Phase 10. Rate limiting is not implemented yet.

## Cloud versus local processing

Only **server mode** exists today. The archive leaves the user's machine and goes to whichever
host runs the CodeAtlas server. When that is `localhost`, nothing leaves the machine. Local
mode (Phase 9) will keep source files on the device. No AI provider is used in this release,
so no code is sent to any third party.

## Reporting

Report suspected vulnerabilities privately to the maintainers rather than in a public issue.
