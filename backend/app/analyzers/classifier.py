"""Classifies a file as source, test, config, documentation, data, asset, generated or other.

The classification is inferred from the file name, extension and path only. Each rule
returns a confidence and a human-readable reason so the UI can show why it was chosen.
Rules run in priority order: generated → config → test → documentation → extension kind.

Folder-level evidence (a whole ``dist/`` of bundles) is handled separately by
``generated_detector``. It reclassifies files inside folders it identifies as build output.
Folder names alone no longer make files "generated": a ``build/`` folder of hand-written
scripts keeps its real classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.analyzers.config_detector import ConfigMatch
from app.analyzers.language_detector import Language
from app.schemas.project import Classification, Confidence


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: Classification
    confidence: Confidence
    reason: str


LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "poetry.lock",
    "pipfile.lock", "uv.lock", "cargo.lock", "composer.lock", "gemfile.lock", "go.sum", "mix.lock",
    "pubspec.lock",
}
BUILD_ARTIFACT_EXTENSIONS = {
    ".pyc", ".pyo", ".class", ".o", ".obj", ".so", ".dylib", ".dll", ".exe", ".a", ".lib", ".jar",
    ".war", ".wasm", ".tsbuildinfo",
}
# Content-hashed bundle names: app.3f9a2c1b.js (webpack, hex) or index-BK3j8d_a.js (Vite/Rollup,
# 8-character base64url). The token must mix letters and digits, so words ("-debounce") and
# dates ("migration-20240101.js") do not match.
HASHED_BUNDLE = re.compile(r"[.-]([0-9a-f]{8,}|[A-Za-z0-9_]{8})\.(m?js|css)$")
CODEGEN_SUFFIXES = ("_pb2.py", "_pb2_grpc.py", ".pb.go", ".pb.cc", ".pb.h", ".g.dart", ".freezed.dart", ".designer.cs")
CODEGEN_INFIX = re.compile(r"\.(generated|gen)\.[a-z0-9]+$")
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing", "e2e"}
DOC_DIRS = {"docs", "doc", "documentation"}
DOC_NAMES = re.compile(r"^(readme|license|licence|changelog|changes|contributing|authors|notice|copying|"
                       r"code_of_conduct|security|history)(\..*)?$")
TEST_NAME_PATTERNS = [
    re.compile(r"^test_.+\.py$"),
    re.compile(r"^.+_test\.(py|go|rb|exs)$"),
    re.compile(r"^.+\.(test|spec)\.[cm]?[jt]sx?$"),
    re.compile(r"^.+(Test|Tests|IT)\.(java|kt|scala|cs)$"),
    re.compile(r"^.+_spec\.rb$"),
    re.compile(r"^.+Tests?\.swift$"),
]
ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".avif", ".tiff",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".webm", ".mov", ".avi",
    ".pdf", ".psd", ".fig", ".sketch",
}
DATA_EXTENSIONS = {".parquet", ".sqlite", ".sqlite3", ".db", ".ndjson", ".jsonl", ".avro", ".pkl", ".npy"}
CONFIG_EXTENSIONS = {".properties", ".env", ".plist"}


def artifact_reason(name: str, extension: str) -> str | None:
    """Why a file name looks like build or generator output, or ``None``. Names only; contents are never read."""
    lowered = name.lower()
    if lowered.endswith((".min.js", ".min.mjs", ".min.css")):
        return "minified bundle"
    if extension == ".map":
        return "source map"
    if extension in BUILD_ARTIFACT_EXTENSIONS:
        return f"compiled artifact ({extension})"
    if lowered.endswith((".chunk.js", ".bundle.js", ".chunk.css")):
        return "hashed bundle"
    hashed = HASHED_BUNDLE.search(name)
    if hashed and any(c.isdigit() for c in hashed.group(1)) and any(c.isalpha() for c in hashed.group(1)):
        return "hashed bundle"
    if lowered.endswith(CODEGEN_SUFFIXES) or CODEGEN_INFIX.search(lowered):
        return "code-generator output"
    return None


def classify(
    name: str,
    extension: str,
    directory_parts: tuple[str, ...],
    language: Language | None,
    config: ConfigMatch | None,
) -> ClassificationResult:
    lowered = name.lower()
    dir_names = {part.lower() for part in directory_parts}

    if lowered in LOCKFILES:
        return ClassificationResult(Classification.GENERATED, Confidence.HIGH, "dependency lockfile")
    artifact = artifact_reason(name, extension)
    if artifact is not None:
        return ClassificationResult(Classification.GENERATED, Confidence.HIGH, f"{artifact} file name")

    if config is not None:
        return ClassificationResult(Classification.CONFIG, Confidence.HIGH, f"recognised file: {config.label}")

    if any(pattern.match(name) for pattern in TEST_NAME_PATTERNS):
        return ClassificationResult(Classification.TEST, Confidence.HIGH, "test file naming convention")
    test_dir = next((part for part in directory_parts if part.lower() in TEST_DIRS), None)
    if test_dir is not None and language is not None and language.kind == "programming":
        return ClassificationResult(Classification.TEST, Confidence.MEDIUM, f"source file inside '{test_dir}/' folder")

    if DOC_NAMES.match(lowered):
        return ClassificationResult(Classification.DOCUMENTATION, Confidence.HIGH, "conventional documentation file name")
    if language is not None and language.kind == "prose":
        return ClassificationResult(Classification.DOCUMENTATION, Confidence.HIGH, f"{language.name} document")
    if dir_names & DOC_DIRS and extension in {".txt", ""}:
        return ClassificationResult(Classification.DOCUMENTATION, Confidence.MEDIUM, "text file inside a docs folder")

    if language is not None:
        if language.kind in ("programming", "markup", "style"):
            return ClassificationResult(Classification.SOURCE, Confidence.HIGH, f"{language.name} source extension")
        if language.kind == "config":
            return ClassificationResult(Classification.CONFIG, Confidence.MEDIUM, f"{language.name} configuration format")
        if language.kind == "data":
            return ClassificationResult(Classification.DATA, Confidence.MEDIUM, f"{language.name} data format")

    if extension in ASSET_EXTENSIONS:
        return ClassificationResult(Classification.ASSET, Confidence.HIGH, f"media or binary asset extension {extension}")
    if extension in DATA_EXTENSIONS:
        return ClassificationResult(Classification.DATA, Confidence.MEDIUM, f"data file extension {extension}")
    if extension in CONFIG_EXTENSIONS:
        return ClassificationResult(Classification.CONFIG, Confidence.MEDIUM, f"configuration extension {extension}")
    if extension == ".txt":
        return ClassificationResult(Classification.DOCUMENTATION, Confidence.LOW, "plain-text file")

    reason = "no extension" if not extension else f"unrecognised extension {extension}"
    return ClassificationResult(Classification.OTHER, Confidence.LOW, reason)
