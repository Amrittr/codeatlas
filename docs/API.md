# API Reference (v0.3, schema version 3)

Base path: `/api`. JSON uses camelCase. There is **no authentication** in this release (see
SECURITY.md). Interactive docs are at `/api/docs` when `CODEATLAS_ENVIRONMENT` is not `production`.

Typical flow:

```
POST /api/projects/analyze      → 202 { job }           (upload + cheap checks)
GET  /api/jobs/{jobId}          → { job } … poll until status is completed / failed / cancelled
GET  /api/projects/{projectId}  → ProjectDetails         (projectId comes from the completed job)
GET  /api/projects/{projectId}/tree | /search | /stats
```

## Errors

Every error has the same shape. `code` is stable and meant for programs; `message` is meant for people:

```json
{ "error": { "code": "unsafe_archive", "message": "The archive contains an entry …", "details": null } }
```

| Status | Codes |
|---|---|
| 400 | `invalid_archive`, `unsafe_archive` |
| 404 | `project_not_found`, `job_not_found`, `node_not_found`, `not_found` |
| 408 | `analysis_timeout` |
| 413 | `upload_too_large`, `archive_uncompressed_too_large`, `suspected_decompression_bomb`, `too_many_files`, `too_many_entries`, `too_many_directories`, `archive_too_deep` |
| 415 | `unsupported_file_type` |
| 422 | `invalid_request` (`details` lists the offending fields), `invalid_patterns`, `tree_too_large` |
| 500 | `internal_error`, with a generic message only |
| 503 | `server_busy` (all analysis slots and queue places in use) |

Problems found **during** a job (for example `unsafe_archive`, `too_many_files`,
`analysis_timeout`) are not HTTP errors. They appear in the job's `error` object with the same
`code`, `message` and the `statusCode` the error would have had.

## `GET /api/health`

`200 {"status": "ok", "version": "0.3.0"}`

## `GET /api/config`

The public limits and defaults the UI needs.

```json
{
  "processingMode": "server",
  "projectTtlSeconds": 1800,
  "limits": { "maxUploadBytes": 104857600, "maxUncompressedBytes": 1073741824, "maxFileBytes": 52428800, "maxFiles": 100000, "maxDepth": 64 },
  "defaultExclusions": [{ "name": "node_modules", "reason": "dependencies", "label": "Installed third-party dependencies" }],
  "patternLimits": { "maxPatterns": 100, "maxPatternLength": 256 }
}
```

## `POST /api/projects/analyze`

`multipart/form-data`:

| Field | Type | Default | Notes |
|---|---|---|---|
| `file` | file, required | | ZIP archive. Detected by its magic bytes; the file name is only displayed. |
| `applyDefaultExclusions` | `true`/`false` | `true` | Skip dependency, VCS, virtualenv and cache folders by name. |
| `respectGitignore` | `true`/`false` | `true` | Apply every `.gitignore` in the archive, using git's rules. |
| `excludePatterns` | text | `""` | Extra gitignore-style patterns, one per line, matched from the archive root. |
| `includePatterns` | text | `""` | Patterns that are always analyzed. They override exclusions, except `__MACOSX/`. |

Pattern fields: at most 100 patterns of 256 characters each (8 KB per field). Blank lines and
`#` comments are ignored. Invalid lists are rejected with `422 invalid_patterns` before a job is created.

The request saves the upload and runs the structural checks synchronously: size, ZIP magic,
end record and central-directory entry count. Failures there return the usual HTTP errors
immediately. Otherwise the response is **`202`**:

```json
{ "job": { "id": "5a4fe415…", "status": "queued", "fileName": "repo.zip", "createdAt": "2026-10-24T07:02:11Z",
           "progress": { "phase": "queued", "current": 0, "total": null, "unit": null },
           "projectId": null, "error": null } }
```

### Exclusion rule order

1. `__MACOSX/` is always excluded.
2. `includePatterns` force a path to be analyzed.
3. `excludePatterns`.
4. Default folder rules (when `applyDefaultExclusions`).
5. `.gitignore` files (when `respectGitignore`). Nested files apply to their own folder, a deeper
   file overrides a shallower one, the last matching line wins, and `!` negates.

As in git, nothing inside an excluded folder is examined, so it cannot be re-included by a
pattern. Include the folder instead. Excluded paths are **not extracted** and do not count
toward `maxFiles`. They still appear in the tree with the rule that matched them.

## `GET /api/jobs/{jobId}`

Returns `{ job }` as above. `status` is one of `queued`, `running`, `completed`, `failed` or `cancelled`.

| `progress.phase` | `total` / `unit` |
|---|---|
| `queued` | waiting for a free worker |
| `inspecting` | — |
| `planning` | archive entries (validation and exclusion rules) |
| `extracting` | files to extract |
| `scanning` | extracted files |
| `indexing` | — (statistics) |
| `done` | — |

`current` and `total` are real counts. `total` is `null` when the phase does not know it.
When `status` is `completed`, `projectId` is set. When it is `failed`, `error` is
`{ "code", "message", "statusCode" }`. Finished job records are kept for
`CODEATLAS_JOB_TTL_SECONDS` (10 min by default).

## `DELETE /api/jobs/{jobId}`

Requests cancellation and returns `202 { job }`. A queued job is cancelled immediately. A
running job stops at its next checkpoint (between archive entries, extracted files and
scanned folders), and its files are deleted. A finished job is returned unchanged.

## `GET /api/projects/{projectId}`

Returns **ProjectDetails**:

```json
{
  "project": {
    "id": "3c38cce2…", "name": "sample-app", "status": "completed",
    "schemaVersion": "3", "processingMode": "server",
    "createdAt": "2026-10-24T06:29:21Z", "expiresAt": "2026-10-24T06:59:21Z",
    "archive": { "fileName": "sample-app.zip", "sizeBytes": 4016, "entryCount": 27 },
    "durations": { "extractMs": 4, "scanMs": 2, "totalMs": 8 },
    "exclusionSettings": { "defaultRules": true, "gitignore": true, "excludePatterns": [], "includePatterns": [],
                           "gitignoreFiles": ["sample-app/.gitignore"] },
    "nodeCount": 37
  },
  "stats": { "totalFiles": 22, "totalDirectories": 12, "totalSizeBytes": 426, "fileTypeCount": 11,
             "sourceFileCount": 9, "testFileCount": 2, "configFileCount": 5, "documentationFileCount": 4,
             "hiddenFileCount": 2, "emptyDirectoryCount": 1, "excludedFileCount": 0, "excludedDirectoryCount": 2,
             "excludedEntryCount": 3, "maxDepth": 4,
             "extensions": [{ "extension": ".js", "fileCount": 4, "sizeBytes": 115 }],
             "languages": [{ "language": "JavaScript", "fileCount": 5, "sizeBytes": 151 }],
             "classifications": [{ "classification": "source", "fileCount": 9, "sizeBytes": 217 }],
             "largestFiles": [{ "nodeId": "n…", "path": "sample-app/src/utils/format.ts", "sizeBytes": 42 }],
             "configFiles": [{ "nodeId": "n…", "path": "sample-app/package.json", "label": "Node.js package manifest", "category": "package_manifest" }],
             "generatedFolders": [], "generatedFolderCount": 0 },
  "exclusions": [{ "nodeId": "n…", "path": "sample-app/node_modules", "type": "directory", "reason": "dependencies",
                   "rule": "default rule: node_modules/", "entryCount": 2 }],
  "exclusionCount": 2,
  "skipped": [{ "path": "sample-app/link", "reason": "symlink_not_followed" }],
  "skippedCount": 1,
  "warnings": [{ "code": "paths_excluded", "message": "2 folders not analyzed …" }]
}
```

Notes:
- All statistics cover **analyzed** paths only. Excluded files and folders are counted in the
  `excluded*` fields. `excludedEntryCount` is the number of archive entries that were not extracted.
- `exclusions[].reason` is `archive_metadata`, `version_control`, `dependencies`,
  `virtual_environment`, `cache`, `build_cache`, `gitignore` or `custom`. `rule` is the exact rule,
  for example `"repo/.gitignore line 3: *.log"` or `"custom rule: docs/"`. At most 500 are listed;
  `exclusionCount` is the total.
- `extensions` uses `"(none)"` for files without an extension and is sorted by file count.
- `generatedFolders` (at most 100; `generatedFolderCount` is the total) lists folders detected as
  build or generator output: `{ nodeId, path, confidence, reason, fileCount }`, for example
  `{"path": "app/dist", "confidence": "high", "reason": "conventional build-output folder name 'dist/'; 3 of 4 files are bundles, source maps or compiled output"}`.
  Only the shallowest such folder is listed. Its analyzed files are reclassified as `generated`
  with the reason `inside generated folder 'app/dist/'`. Detection uses names only, and the
  folders are still analyzed.
- `skipped` lists at most 200 entries; `skippedCount` is the full total. Skip reasons:
  `symlink_not_followed`, `special_file`, `encrypted`, `case_collision`, `duplicate_entry`,
  `path_conflict`, `file_too_large`, `unsupported_compression`, `corrupt_entry`, `unsafe_name`,
  `name_too_long`, `path_too_long`.
- Warning codes: `empty_project`, `paths_excluded`, `gitignore_not_applied` (a `.gitignore` over
  256 KB, unreadable, or past the 500-file cap), `entries_skipped`, `possible_secrets`.

`404 project_not_found` once expired or deleted. `projectId` must be 32 lower-case hex digits,
otherwise the response is `422`.

## `DELETE /api/projects/{projectId}`

Removes the analysis from memory right away. Returns `204`.

## `GET /api/projects/{projectId}/stats`

The `stats` object only.

## `GET /api/projects/{projectId}/tree`

| Query | Default | Meaning |
|---|---|---|
| `nodeId` | root | Start node |
| `depth` | `1` | Levels below the start node to include (0–1024) |
| `reveal` | `false` | Also include every ancestor and the ancestors' children |

```json
{
  "projectId": "…", "rootId": "root",
  "nodes": [ { "id": "root", "type": "directory", "name": "sample-app.zip", "path": "", "parentId": null, "depth": 0, "hidden": false,
               "childCount": 1, "descendantFileCount": 22, "descendantDirectoryCount": 12, "sizeBytes": 426,
               "excluded": false, "excludedReason": null, "excludedRule": null, "excludedEntryCount": null,
               "generated": false, "generatedConfidence": null, "generatedReason": null },
             { "id": "n…", "type": "file", "name": "debug.log", "path": "repo/src/debug.log", "parentId": "n…", "depth": 3, "hidden": false,
               "extension": ".log", "sizeBytes": null, "modifiedAt": null, "language": null,
               "classification": "other", "classificationConfidence": "low", "classificationReason": "unrecognised extension .log",
               "excluded": true, "excludedReason": "gitignore", "excludedRule": "repo/.gitignore line 1: *.log" } ],
  "children": { "root": ["n…"] }
}
```

Requests that would return more than 25,000 nodes (`CODEATLAS_MAX_TREE_RESPONSE_NODES`) are
refused with `422 tree_too_large`; ask for a smaller depth. Children are ordered folders first,
then by natural, case-insensitive name (`module2` before `module10`).

`children` holds the complete, ordered child list for every directory whose children are in
`nodes`. A directory missing from `children` has not been loaded. Use its `childCount` to
decide whether it can be expanded. Excluded files have `sizeBytes: null`, because they were
never extracted. Directory counts and sizes include analyzed descendants only.

## `GET /api/projects/{projectId}/search`

| Query | Default | Meaning |
|---|---|---|
| `q` | `""` | Case-insensitive substring of the name, or of the path when `q` contains `/` (max 200 chars) |
| `extension` | (none) | Repeatable. `.py`, `py` and `(none)` are all accepted |
| `classification` | (none) | Repeatable: `source`, `test`, `config`, `documentation`, `data`, `asset`, `generated`, `other` |
| `type` | `all` | `all`, `file` or `directory` |
| `limit` | `500` | 1–2000 |

The response has the same shape as `/tree`, plus `matchIds`, `totalMatches` and `truncated`.
`nodes` contains the matches and all their ancestors. `children` holds only the pruned
child lists, so the result renders as a filtered tree. Extension and classification filters
only ever match files. Excluded paths can match and are marked `excluded`.
