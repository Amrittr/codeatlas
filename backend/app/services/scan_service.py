"""Filesystem scanner: walks a directory and builds the normalised project node list.

Independent of how the files arrived. ZIP import uses it today, and a local agent can
reuse it later. It calls ``lstat`` only and never opens file contents, except
``.gitignore`` files when it applies an exclusion policy itself (local mode). Symlinks are
reported and not followed.

Two ways to mark exclusions:
- ``excluded_entries`` (archive mode): the importer already applied the policy and did not
  extract excluded paths. Excluded folders exist on disk as empty placeholders; excluded files
  do not exist on disk and are added to the tree from these records.
- ``policy`` (local mode): the scanner applies the policy itself while walking.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.analyzers.classifier import classify
from app.analyzers.config_detector import detect_config
from app.analyzers.exclusions import MAX_GITIGNORE_BYTES, ExclusionPolicy
from app.analyzers.language_detector import detect_language
from app.core.errors import AppError
from app.services.nodes import DirectoryRecord, FileRecord
from app.services.analysis_context import AnalysisContext
from app.services.archive_service import ExcludedEntry

ROOT_ID = "root"


def node_id(path: str) -> str:
    """Stable id derived from the relative path, so re-analysing the same tree gives the same ids."""
    if not path:
        return ROOT_ID
    return "n" + hashlib.blake2b(path.encode("utf-8"), digest_size=8).hexdigest()


def split_extension(name: str) -> str:
    _, extension = os.path.splitext(name)
    return extension.lower()


_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str) -> tuple:
    """Case-insensitive natural order, as file explorers use: module2 before module10."""
    return tuple(int(part) if part.isdigit() else part for part in _DIGITS.split(name.casefold()))


@dataclass
class ScanResult:
    nodes: dict[str, FileRecord | DirectoryRecord]
    children: dict[str, list[str]]
    skipped: list[tuple[str, str]] = field(default_factory=list)
    duration_ms: int = 0


@dataclass(slots=True)
class _Item:
    """One child of a folder: a real filesystem entry, or an excluded file the importer did not extract."""

    name: str
    is_dir: bool
    entry: os.DirEntry[str] | None = None
    excluded: ExcludedEntry | None = None

    def sort_key(self) -> tuple:
        return (0 if self.is_dir else 1, natural_key(self.name), self.name)


def _file_node(
    name: str,
    path: str,
    parent_id: str,
    rel_parts: tuple[str, ...],
    *,
    size: int | None,
    mtime: float | None,
    excluded_reason: str | None = None,
    excluded_rule: str | None = None,
) -> FileRecord:
    extension = split_extension(name)
    language = detect_language(name, extension)
    result = classify(name, extension, rel_parts, language, detect_config(name, path))
    return FileRecord(
        id=node_id(path),
        name=name,
        path=path,
        parent_id=parent_id,
        depth=len(rel_parts) + 1,
        hidden=name.startswith("."),
        extension=extension,
        size_bytes=size,
        modified_at=datetime.fromtimestamp(mtime, UTC).replace(tzinfo=None) if mtime is not None else None,
        language=language.name if language else None,
        classification=result.classification,
        classification_confidence=result.confidence,
        classification_reason=result.reason,
        excluded=excluded_reason is not None,
        excluded_reason=excluded_reason,
        excluded_rule=excluded_rule,
    )


def scan_directory(
    root: Path,
    *,
    root_name: str,
    context: AnalysisContext,
    max_files: int,
    max_depth: int,
    excluded_entries: dict[str, ExcludedEntry] | None = None,
    policy: ExclusionPolicy | None = None,
) -> ScanResult:
    """Scan ``root`` recursively. Children are sorted folders first, then in natural name order."""
    started = time.perf_counter()
    excluded_entries = excluded_entries or {}
    excluded_files_by_parent: dict[str, list[tuple[str, ExcludedEntry]]] = {}
    for path, record in excluded_entries.items():
        if record.kind == "file":
            parent, _, name = path.rpartition("/")
            excluded_files_by_parent.setdefault(parent, []).append((name, record))

    nodes: dict[str, FileRecord | DirectoryRecord] = {}
    children: dict[str, list[str]] = {}
    skipped: list[tuple[str, str]] = []
    file_count = 0

    nodes[ROOT_ID] = DirectoryRecord(id=ROOT_ID, name=root_name, path="", parent_id=None, depth=0, hidden=False)
    children[ROOT_ID] = []
    # Stack of (absolute directory, relative path parts, node id) in pre-order.
    stack: list[tuple[str, tuple[str, ...], str]] = [(os.fspath(root), (), ROOT_ID)]

    while stack:
        absolute, rel_parts, dir_id = stack.pop()
        context.checkpoint()
        dir_path = "/".join(rel_parts)
        try:
            with os.scandir(absolute) as iterator:
                entries = list(iterator)
        except PermissionError:
            skipped.append((dir_path or ".", "permission_denied"))
            continue

        if policy is not None and policy.respect_gitignore:
            _load_local_gitignore(absolute, rel_parts, policy)

        items: list[_Item] = []
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            items.append(_Item(entry.name, is_dir, entry=entry))
        items.extend(_Item(name, False, excluded=record) for name, record in excluded_files_by_parent.get(dir_path, ()))
        items.sort(key=_Item.sort_key)

        subdirectories: list[tuple[str, tuple[str, ...], str]] = []
        for item in items:
            parts = (*rel_parts, item.name)
            path = "/".join(parts)
            depth = len(parts)

            if item.excluded is not None:  # excluded file recorded by the importer
                nodes[node_id(path)] = _file_node(
                    item.name, path, dir_id, rel_parts, size=None, mtime=None,
                    excluded_reason=item.excluded.reason, excluded_rule=item.excluded.rule,
                )
                children[dir_id].append(node_id(path))
                continue

            entry = item.entry
            try:
                if entry.is_symlink():
                    skipped.append((path, "symlink_not_followed"))
                    continue
                info = entry.stat(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except PermissionError:
                skipped.append((path, "permission_denied"))
                continue
            except OSError:
                skipped.append((path, "unreadable"))
                continue

            child_id = node_id(path)
            match = policy.match(parts, item.is_dir) if policy is not None else None
            if item.is_dir:
                if depth > max_depth:
                    raise AppError("archive_too_deep", f"The project nests folders deeper than {max_depth} levels.", 413)
                record = excluded_entries.get(path)
                if record is not None and record.kind == "directory":
                    reason, rule, entry_count = record.reason, record.rule, record.entry_count
                elif match is not None:
                    reason, rule, entry_count = match.reason, match.rule, None
                else:
                    reason = rule = entry_count = None
                nodes[child_id] = DirectoryRecord(
                    id=child_id,
                    name=item.name,
                    path=path,
                    parent_id=dir_id,
                    depth=depth,
                    hidden=item.name.startswith("."),
                    excluded=reason is not None,
                    excluded_reason=reason,
                    excluded_rule=rule,
                    excluded_entry_count=entry_count,
                )
                children[dir_id].append(child_id)
                children[child_id] = []
                if reason is None:
                    subdirectories.append((entry.path, parts, child_id))
            elif is_file:
                if match is None:
                    file_count += 1
                    if file_count > max_files:
                        raise AppError("too_many_files", f"The project contains more than {max_files:,} files.", 413)
                    context.advance()
                nodes[child_id] = _file_node(
                    item.name, path, dir_id, rel_parts, size=info.st_size, mtime=info.st_mtime,
                    excluded_reason=match.reason if match else None, excluded_rule=match.rule if match else None,
                )
                children[dir_id].append(child_id)
            else:
                skipped.append((path, "special_file"))

        # Push in reverse so the first sorted subdirectory is scanned next (stable pre-order).
        stack.extend(reversed(subdirectories))

    _aggregate(nodes, children)
    return ScanResult(
        nodes=nodes,
        children=children,
        skipped=skipped,
        duration_ms=round((time.perf_counter() - started) * 1000),
    )


def _load_local_gitignore(absolute: str, rel_parts: tuple[str, ...], policy: ExclusionPolicy) -> None:
    path = os.path.join(absolute, ".gitignore")
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_GITIGNORE_BYTES:
            return
        with open(path, "rb") as handle:
            policy.add_gitignore(rel_parts, handle.read(MAX_GITIGNORE_BYTES).decode("utf-8", errors="replace"))
    except OSError:
        return


def _aggregate(nodes: dict[str, FileRecord | DirectoryRecord], children: dict[str, list[str]]) -> None:
    """Fill directory counts and sizes bottom-up. Deepest directories are processed first.

    Excluded files and folders are children (they appear in the tree) but add nothing to
    file counts or sizes, because they were not analyzed.
    """
    directories = sorted(
        (node for node in nodes.values() if isinstance(node, DirectoryRecord)),
        key=lambda node: node.depth,
        reverse=True,
    )
    for directory in directories:
        files = dirs = size = 0
        for child_id in children[directory.id]:
            child = nodes[child_id]
            if isinstance(child, FileRecord):
                if not child.excluded:
                    files += 1
                    size += child.size_bytes or 0
            elif not child.excluded:
                dirs += 1 + child.descendant_directory_count
                files += child.descendant_file_count
                size += child.size_bytes
        directory.child_count = len(children[directory.id])
        directory.descendant_file_count = files
        directory.descendant_directory_count = dirs
        directory.size_bytes = size
