"""API data contract for analyzed projects. JSON keys are camelCase; Python attributes are snake_case.

Fields fall into two groups, and the frontend presents them differently:
- Observed facts read from the archive/filesystem: name, path, size, depth, timestamps, counts.
- Inferences from names and extensions: ``language`` and ``classification`` (with confidence + reason).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = "3"


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


class Classification(StrEnum):
    SOURCE = "source"
    TEST = "test"
    CONFIG = "config"
    DOCUMENTATION = "documentation"
    DATA = "data"
    ASSET = "asset"
    GENERATED = "generated"
    OTHER = "other"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NodeBase(CamelModel):
    id: str
    name: str
    path: str = Field(description="Path relative to the project root, '/'-separated. The root is ''.")
    parent_id: str | None
    depth: int
    hidden: bool


class FileNode(NodeBase):
    type: Literal["file"] = "file"
    extension: str = Field(description="Lower-case extension including the dot, or '' when there is none.")
    size_bytes: int | None = Field(description="Observed size. null for excluded files, which were never extracted.")
    modified_at: datetime | None = Field(
        default=None, description="Timestamp recorded in the archive; the archive format carries no timezone."
    )
    language: str | None = None
    classification: Classification
    classification_confidence: Confidence
    classification_reason: str
    excluded: bool = False
    excluded_reason: str | None = None
    excluded_rule: str | None = Field(default=None, description="The exact rule that excluded this path.")


class DirectoryNode(NodeBase):
    type: Literal["directory"] = "directory"
    child_count: int = 0
    descendant_file_count: int = 0
    descendant_directory_count: int = 0
    size_bytes: int = 0
    excluded: bool = False
    excluded_reason: str | None = None
    excluded_rule: str | None = None
    generated: bool = False
    generated_confidence: Confidence | None = None
    generated_reason: str | None = Field(default=None, description="Evidence for the generated-output verdict.")
    excluded_entry_count: int | None = Field(
        default=None, description="Archive entries under an excluded directory. They were not extracted."
    )


Node = Annotated[FileNode | DirectoryNode, Field(discriminator="type")]


class ArchiveInfo(CamelModel):
    file_name: str
    size_bytes: int
    entry_count: int


class Durations(CamelModel):
    extract_ms: int
    scan_ms: int
    total_ms: int


class ExclusionSettings(CamelModel):
    default_rules: bool
    gitignore: bool
    exclude_patterns: list[str]
    include_patterns: list[str]
    gitignore_files: list[str] = Field(description="The .gitignore files that were applied.")


class ProjectSummary(CamelModel):
    id: str
    name: str
    status: Literal["completed"] = "completed"
    schema_version: str = SCHEMA_VERSION
    processing_mode: Literal["server"] = "server"
    created_at: datetime
    expires_at: datetime
    archive: ArchiveInfo
    durations: Durations
    exclusion_settings: ExclusionSettings
    node_count: int


class ExtensionStat(CamelModel):
    extension: str
    file_count: int
    size_bytes: int


class LanguageStat(CamelModel):
    language: str
    file_count: int
    size_bytes: int


class ClassificationStat(CamelModel):
    classification: Classification
    file_count: int
    size_bytes: int


class FileRef(CamelModel):
    node_id: str
    path: str
    size_bytes: int


class GeneratedFolderStat(CamelModel):
    node_id: str
    path: str
    confidence: Confidence
    reason: str
    file_count: int


class ConfigFileStat(CamelModel):
    node_id: str
    path: str
    label: str
    category: str


class ProjectStats(CamelModel):
    total_files: int
    total_directories: int
    total_size_bytes: int
    file_type_count: int
    source_file_count: int
    test_file_count: int
    config_file_count: int
    documentation_file_count: int
    hidden_file_count: int
    empty_directory_count: int
    excluded_file_count: int
    excluded_directory_count: int
    excluded_entry_count: int = Field(description="Archive entries not extracted because of exclusions.")
    max_depth: int
    extensions: list[ExtensionStat]
    languages: list[LanguageStat]
    classifications: list[ClassificationStat]
    largest_files: list[FileRef]
    config_files: list[ConfigFileStat]
    generated_folders: list[GeneratedFolderStat]
    generated_folder_count: int


class Exclusion(CamelModel):
    node_id: str
    path: str
    type: Literal["file", "directory"]
    reason: str
    rule: str | None
    entry_count: int | None


class SkippedEntry(CamelModel):
    path: str
    reason: str


class AnalysisWarning(CamelModel):
    code: str
    message: str


class ProjectDetails(CamelModel):
    project: ProjectSummary
    stats: ProjectStats
    exclusions: list[Exclusion]
    exclusion_count: int
    skipped: list[SkippedEntry]
    skipped_count: int
    warnings: list[AnalysisWarning]


class TreeResponse(CamelModel):
    project_id: str
    root_id: str
    nodes: list[Node]
    children: dict[str, list[str]] = Field(
        description="Ordered child ids for every directory whose children are included in this response."
    )


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobProgress(CamelModel):
    phase: str
    current: int
    total: int | None
    unit: str | None


class JobError(CamelModel):
    code: str
    message: str
    status_code: int


class JobView(CamelModel):
    id: str
    status: JobStatus
    file_name: str
    created_at: datetime
    progress: JobProgress
    project_id: str | None = None
    error: JobError | None = None


class JobResponse(CamelModel):
    job: JobView


class SearchResponse(TreeResponse):
    match_ids: list[str]
    total_matches: int
    truncated: bool
