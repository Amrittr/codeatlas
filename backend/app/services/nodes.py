"""Compact in-memory node records.

A stored analysis keeps one record per file and folder for as long as the project lives. Pydantic
models cost about 1.5 KB each; these slotted dataclasses cost about 0.4 KB (measured with
tracemalloc on 20k nodes). The API contract stays the Pydantic models in ``schemas.project``.
``to_api`` converts only the slice a response actually returns.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import ClassVar

from app.schemas.project import Classification, Confidence, DirectoryNode, FileNode


@dataclass(slots=True)
class FileRecord:
    type: ClassVar[str] = "file"

    id: str
    name: str
    path: str
    parent_id: str | None
    depth: int
    hidden: bool
    extension: str
    size_bytes: int | None
    modified_at: datetime | None
    language: str | None
    classification: Classification
    classification_confidence: Confidence
    classification_reason: str
    excluded: bool = False
    excluded_reason: str | None = None
    excluded_rule: str | None = None


@dataclass(slots=True)
class DirectoryRecord:
    type: ClassVar[str] = "directory"

    id: str
    name: str
    path: str
    parent_id: str | None
    depth: int
    hidden: bool
    child_count: int = 0
    descendant_file_count: int = 0
    descendant_directory_count: int = 0
    size_bytes: int = 0
    excluded: bool = False
    excluded_reason: str | None = None
    excluded_rule: str | None = None
    generated: bool = False
    generated_confidence: Confidence | None = None
    generated_reason: str | None = None
    excluded_entry_count: int | None = None


NodeRecord = FileRecord | DirectoryRecord

_FILE_FIELDS = tuple(field.name for field in fields(FileRecord))
_DIRECTORY_FIELDS = tuple(field.name for field in fields(DirectoryRecord))


def to_api(node: NodeRecord) -> FileNode | DirectoryNode:
    """Build the response model without re-validating values the scanner already produced."""
    if isinstance(node, FileRecord):
        return FileNode.model_construct(**{name: getattr(node, name) for name in _FILE_FIELDS})
    return DirectoryNode.model_construct(**{name: getattr(node, name) for name in _DIRECTORY_FIELDS})
