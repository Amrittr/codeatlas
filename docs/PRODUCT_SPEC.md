# CodeAtlas — Product Specification

## Problem

When developers leave or change teams, their code stays in the repository but much of their
practical understanding leaves with them. A new developer has to work out the structure, the
technologies, the entry points, how modules fit together and where features live. In a large
repository that can take days or weeks. File explorers show *where* files are, not *how the
project fits together*.

## Mission

Help a developer understand an unfamiliar codebase without depending on the person who wrote it.

## Target users

Primary: software companies onboarding developers into existing projects. Also developers
joining unfamiliar repositories, teams maintaining legacy systems, tech leads reviewing
architectures, consultants analyzing client code, and teams writing technical documentation.

## Product principles

1. Accuracy before visual complexity.
2. Useful project analysis before AI-generated explanations.
3. Interactive exploration rather than information dumps.
4. Security and confidentiality of source code.
5. Built for large repositories, with scale that is measured, not assumed.
6. Modular, maintainable architecture.
7. Observed facts kept apart from inferences.
8. Working software at every milestone.
9. Never claim a feature works unless it is implemented and tested.
10. Never execute uploaded source code during analysis.

## Capabilities and boundaries

| Capability | Status |
|---|---|
| ZIP upload with secure extraction | **Available (v0.1)** |
| Recursive structure scan, file/folder metadata | **Available** |
| Project statistics (counts, sizes, extensions, classifications, languages) | **Available** |
| Interactive file tree with search, filters, lazy loading, virtualisation | **Available** |
| Default exclusions shown in the UI | **Available** |
| Configuration-file recognition (by name) | **Available** (Phase 4 deepens it) |
| Configurable exclusions, `.gitignore`, background jobs, larger repos | Planned: Phase 2 |
| GitHub repository import | Planned: Phase 3 |
| Framework, build-system and entry-point detection with evidence | Planned: Phase 4 |
| Parsing and symbol indexing (JS/TS/Python/Java first) | Planned: Phase 5 |
| Dependency graph (imports/exports with evidence) | Planned: Phase 6 |
| Architecture map | Planned: Phase 7 |
| AI codebase assistant grounded in the index | Planned: Phase 8 |
| Local analysis agent (source stays on device) | Planned: Phase 9 |
| Accounts, teams, persistence, enterprise controls | Planned: Phase 10 |

## Processing modes

- **Server mode (the only mode today).** The archive is uploaded to the CodeAtlas server,
  extracted to a private temporary folder, scanned, and deleted before the response is sent.
  Only metadata (names, paths, sizes, classifications) is kept, in memory, for a limited time.
- **Local mode (Phase 9).** A local agent scans the project on the user's machine. Only
  explicitly permitted metadata leaves the device.

## What "done" means for the MVP

A developer can clone CodeAtlas, install it, start it locally, upload a real project ZIP and
then: see the real hierarchy; expand and collapse folders; search and filter by extension;
see accurate counts and file-type statistics; see which folders were excluded; and get
clear errors for invalid uploads. No AI or GitHub integration is needed.
