"""Analysis pipeline: archive → secure extraction → filesystem scan → statistics → index.

The caller owns the work directory (see ``job_service``) and removes it, with the
extracted source files in it, as soon as this function returns or raises.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.analyzers.exclusions import REASON_LABELS, ExclusionPolicy, PatternError, parse_pattern_text
from app.analyzers.generated_detector import detect_generated_folders
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.project import (
    AnalysisWarning,
    ArchiveInfo,
    Durations,
    Exclusion,
    ExclusionSettings,
    ProjectDetails,
    ProjectSummary,
    SkippedEntry,
)
from app.services.nodes import DirectoryRecord, FileRecord
from app.services.analysis_context import AnalysisContext
from app.services.archive_service import display_name, extract_archive
from app.services.project_index import ProjectIndex
from app.services.scan_service import ROOT_ID, scan_directory
from app.services.statistics_service import compute_statistics

logger = logging.getLogger("codeatlas.analysis")

MAX_LISTED_SKIPPED = 200
MAX_LISTED_EXCLUSIONS = 500
MAX_PATTERN_TEXT = 8192


@dataclass(frozen=True)
class AnalysisOptions:
    apply_default_rules: bool = True
    respect_gitignore: bool = True
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)

    @classmethod
    def from_form(cls, *, apply_default_rules: bool, respect_gitignore: bool, exclude_text: str, include_text: str) -> AnalysisOptions:
        """Parse and validate user-supplied patterns. Raises ``AppError`` (422) with a readable message."""
        try:
            options = cls(
                apply_default_rules=apply_default_rules,
                respect_gitignore=respect_gitignore,
                exclude_patterns=parse_pattern_text(exclude_text, label="Exclude patterns"),
                include_patterns=parse_pattern_text(include_text, label="Include patterns"),
            )
            options.policy()  # compile once now so invalid patterns fail the request, not the job
        except PatternError as error:
            raise AppError("invalid_patterns", str(error), 422) from None
        return options

    def policy(self) -> ExclusionPolicy:
        return ExclusionPolicy(
            apply_default_rules=self.apply_default_rules,
            respect_gitignore=self.respect_gitignore,
            exclude_patterns=list(self.exclude_patterns),
            include_patterns=list(self.include_patterns),
        )


def safe_upload_name(raw: str | None) -> str:
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = display_name(name).strip() or "upload.zip"
    return name[:255]


def _archive_stem(file_name: str) -> str:
    stem = re.sub(r"\.zip$", "", file_name, flags=re.IGNORECASE)
    return stem or "project"


def analyze_archive(
    archive_path: Path,
    extract_dir: Path,
    file_name: str,
    settings: Settings,
    options: AnalysisOptions,
    context: AnalysisContext,
) -> tuple[ProjectDetails, ProjectIndex]:
    started = time.perf_counter()
    policy = options.policy()

    with archive_path.open("rb") as fp:
        report = extract_archive(fp, extract_dir, settings, policy, context)
    extract_ms = round((time.perf_counter() - started) * 1000)

    context.set_phase("scanning", total=report.extracted_file_count)
    scan = scan_directory(
        extract_dir,
        root_name=file_name,
        context=context,
        excluded_entries=report.excluded,
        max_files=settings.max_files,
        max_depth=settings.max_depth,
    )

    context.set_phase("indexing")
    context.checkpoint()
    nodes = scan.nodes
    excluded_entry_count = sum(item.entry_count for item in report.excluded.values())
    generated_folders = detect_generated_folders(nodes, scan.children, ROOT_ID)
    stats = compute_statistics(
        nodes, ROOT_ID, excluded_entry_count=excluded_entry_count, generated_folders=generated_folders
    )
    index = ProjectIndex(nodes, scan.children, ROOT_ID)

    skipped_pairs = [*report.skipped, *scan.skipped]
    exclusions = sorted(
        (
            Exclusion(
                node_id=node.id,
                path=node.path,
                type=node.type,
                reason=node.excluded_reason or "excluded",
                rule=node.excluded_rule,
                entry_count=node.excluded_entry_count if isinstance(node, DirectoryRecord) else None,
            )
            for node in nodes.values()
            if node.excluded
        ),
        key=lambda item: item.path,
    )

    now = datetime.now(UTC)
    summary = ProjectSummary(
        id=uuid.uuid4().hex,
        name=_project_name(nodes, scan.children, _archive_stem(file_name)),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.project_ttl_seconds),
        archive=ArchiveInfo(file_name=file_name, size_bytes=report.archive_size, entry_count=report.entry_count),
        durations=Durations(
            extract_ms=extract_ms,
            scan_ms=scan.duration_ms,
            total_ms=round((time.perf_counter() - started) * 1000),
        ),
        exclusion_settings=ExclusionSettings(
            default_rules=options.apply_default_rules,
            gitignore=options.respect_gitignore,
            exclude_patterns=list(options.exclude_patterns),
            include_patterns=list(options.include_patterns),
            gitignore_files=policy.gitignore_sources,
        ),
        node_count=len(nodes),
    )
    details = ProjectDetails(
        project=summary,
        stats=stats,
        exclusions=exclusions[:MAX_LISTED_EXCLUSIONS],
        exclusion_count=len(exclusions),
        skipped=[SkippedEntry(path=path, reason=reason) for path, reason in skipped_pairs[:MAX_LISTED_SKIPPED]],
        skipped_count=len(skipped_pairs),
        warnings=_warnings(nodes, stats, exclusions, len(skipped_pairs), report.gitignore_problems),
    )
    logger.info(
        "Analyzed project %s: %d files, %d directories, %d excluded, %d skipped, %d ms",
        summary.id, stats.total_files, stats.total_directories, len(exclusions), len(skipped_pairs),
        summary.durations.total_ms,
    )
    return details, index


def _project_name(nodes: dict, children: dict[str, list[str]], fallback: str) -> str:
    """Use the single top-level folder (e.g. GitHub's ``repo-main/``) when the archive has one."""
    top = children.get(ROOT_ID, [])
    if len(top) == 1 and isinstance(nodes[top[0]], DirectoryRecord) and not nodes[top[0]].excluded:
        return nodes[top[0]].name
    return fallback


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count:,} {singular if count == 1 else plural}"


def _warnings(nodes: dict, stats, exclusions: list[Exclusion], skipped_count: int, gitignore_problems) -> list[AnalysisWarning]:
    warnings: list[AnalysisWarning] = []
    if stats.total_files == 0:
        warnings.append(AnalysisWarning(code="empty_project", message="The archive contains no files to analyze."))
    if exclusions:
        parts = []
        if stats.excluded_directory_count:
            parts.append(_plural(stats.excluded_directory_count, "folder", "folders"))
        if stats.excluded_file_count:
            parts.append(_plural(stats.excluded_file_count, "file", "files"))
        reasons = sorted({REASON_LABELS.get(item.reason, item.reason).lower() for item in exclusions})
        entries = stats.excluded_entry_count
        warnings.append(
            AnalysisWarning(
                code="paths_excluded",
                message=f"{' and '.join(parts)} not analyzed ({'; '.join(reasons)}). "
                f"{_plural(entries, 'archive entry was', 'archive entries were')} not extracted.",
            )
        )
    for path, problem in gitignore_problems:
        warnings.append(AnalysisWarning(code="gitignore_not_applied", message=f"{path}: {problem}."))
    if skipped_count:
        warnings.append(
            AnalysisWarning(
                code="entries_skipped",
                message=f"{_plural(skipped_count, 'archive entry was', 'archive entries were')} skipped "
                "for safety or integrity reasons. They are not in the tree.",
            )
        )
    if any(isinstance(node, FileRecord) and not node.excluded and _looks_like_env_file(node.name) for node in nodes.values()):
        warnings.append(
            AnalysisWarning(
                code="possible_secrets",
                message="The project contains .env files, which often hold secrets. CodeAtlas recorded only "
                "their names and sizes; their contents were not read and have already been deleted.",
            )
        )
    return warnings


def _looks_like_env_file(name: str) -> bool:
    lowered = name.lower()
    if lowered.endswith((".example", ".sample", ".template", ".dist")):
        return False
    return lowered == ".env" or lowered.startswith(".env.")


def remove_workdir(workdir: Path) -> None:
    def on_error(function, path, exc) -> None:  # noqa: ANN001 - shutil callback signature
        logger.warning("Could not remove part of a temporary analysis directory (%s)", type(exc).__name__)

    shutil.rmtree(workdir, onexc=on_error)
    if os.path.exists(workdir):
        logger.error("Temporary analysis directory was not fully removed")
