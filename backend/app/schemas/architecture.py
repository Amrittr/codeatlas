"""API contract for the generated architecture map (GET /api/projects/{id}/architecture)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.project import CamelModel, Confidence


class Evidence(CamelModel):
    kind: Literal["import", "manifest", "file-types", "convention", "structure", "entry-point"]
    detail: str
    path: str | None = None
    node_id: str | None = None
    line: int | None = None


class Framework(CamelModel):
    name: str
    role: str
    confidence: Confidence
    importing_files: int
    declared_in: list[str]


class LanguageCount(CamelModel):
    language: str
    file_count: int


class EntryPoint(CamelModel):
    path: str
    node_id: str | None
    reason: str


class Component(CamelModel):
    id: str
    name: str
    path: str = Field(description="Folder the component covers ('' for the archive root).")
    node_id: str | None
    package_name: str | None = None
    role: str
    role_label: str
    confidence: Confidence
    evidence: list[Evidence]
    file_count: int
    parsed_file_count: int
    languages: list[LanguageCount]
    frameworks: list[str]
    entry_points: list[EntryPoint]


class External(CamelModel):
    id: str
    category: str
    name: str = Field(description="Category label, e.g. 'Databases'.")
    services: list[str] = Field(description="Detected services, e.g. ['PostgreSQL (pg)', 'Redis (ioredis)'].")


class EdgeEvidence(CamelModel):
    path: str
    node_id: str | None
    line: int
    specifier: str
    target: str


class Connection(CamelModel):
    id: str
    source: str
    target: str
    target_type: Literal["component", "external"]
    import_count: int
    file_count: int
    kinds: list[str]
    confidence: Confidence
    evidence: list[EdgeEvidence]


class ArchitectureSummary(CamelModel):
    code_files: int
    parsed_files: int
    parse_errors: int
    partially_parsed: int
    skipped_too_large: int
    imports: int
    internal_imports: int
    external_packages: int
    unresolved_imports: int
    dynamic_unknown: int
    languages: list[LanguageCount]


class ArchitectureResponse(CamelModel):
    project_id: str
    status: Literal["available", "no_code", "disabled"]
    summary: ArchitectureSummary
    frameworks: list[Framework]
    components: list[Component]
    externals: list[External]
    connections: list[Connection]
    unresolved_samples: list[EdgeEvidence]
    notes: list[str]


class ComponentFile(CamelModel):
    node_id: str | None
    path: str
    language: str | None
    imports_internal: int
    imported_by: int
    external_packages: list[str]
    parse_status: Literal["parsed", "partial", "error", "too_large", "not_parsed"]


class ComponentDetails(CamelModel):
    component: Component
    files: list[ComponentFile]
    total_files: int
