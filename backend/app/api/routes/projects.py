from __future__ import annotations

import tempfile
from pathlib import Path as FsPath
from typing import Annotated, BinaryIO, Literal

from fastapi import APIRouter, File, Form, Path, Query, Request, Response, UploadFile

from app.core.config import Settings
from app.core.errors import AppError
from app.repositories.project_store import ProjectStore, StoredProject
from app.schemas.project import (
    Classification,
    JobResponse,
    ProjectDetails,
    ProjectStats,
    SearchResponse,
    TreeResponse,
)
from app.services.analysis_service import MAX_PATTERN_TEXT, AnalysisOptions, remove_workdir, safe_upload_name
from app.services.archive_service import inspect_archive
from app.services.nodes import to_api
from app.services.statistics_service import NO_EXTENSION

router = APIRouter(prefix="/api/projects", tags=["projects"])

ProjectId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="Id returned by POST /api/projects/analyze")]
MAX_TREE_DEPTH = 1024
MAX_SEARCH_LIMIT = 2000


def _store(request: Request) -> ProjectStore:
    return request.app.state.store


def _load(request: Request, project_id: str) -> StoredProject:
    stored = _store(request).get(project_id)
    if stored is None:
        raise AppError(
            "project_not_found",
            "This analysis does not exist or has expired. Upload the archive again.",
            404,
        )
    return stored


@router.post("/analyze", response_model=JobResponse, status_code=202)
def analyze(
    request: Request,
    file: Annotated[UploadFile, File(description="ZIP archive of the project")],
    apply_default_exclusions: Annotated[bool, Form(alias="applyDefaultExclusions")] = True,
    respect_gitignore: Annotated[bool, Form(alias="respectGitignore")] = True,
    exclude_patterns: Annotated[str, Form(alias="excludePatterns", max_length=MAX_PATTERN_TEXT)] = "",
    include_patterns: Annotated[str, Form(alias="includePatterns", max_length=MAX_PATTERN_TEXT)] = "",
) -> JobResponse:
    """Accept an archive and start a background analysis job.

    Cheap checks (size, ZIP structure, entry count, pattern syntax) run here so bad uploads
    fail immediately. Everything else happens in the job: poll ``GET /api/jobs/{id}``.
    """
    settings: Settings = request.app.state.settings
    options = AnalysisOptions.from_form(
        apply_default_rules=apply_default_exclusions,
        respect_gitignore=respect_gitignore,
        exclude_text=exclude_patterns,
        include_text=include_patterns,
    )
    workdir = FsPath(tempfile.mkdtemp(prefix="codeatlas-", dir=settings.temp_dir))
    try:
        archive_path = workdir / "upload.zip"
        _save_upload(file.file, archive_path, settings.max_upload_bytes)
        with archive_path.open("rb") as fp:
            inspect_archive(fp, settings)
        job = request.app.state.jobs.submit(workdir, archive_path, safe_upload_name(file.filename), options)
    except BaseException:
        remove_workdir(workdir)
        raise
    return JobResponse(job=job.view())


def _save_upload(source: BinaryIO, target: FsPath, limit: int) -> None:
    """Copy the spooled upload into the job's private directory, enforcing the size limit."""
    source.seek(0)
    copied = 0
    with target.open("xb") as sink:
        while chunk := source.read(1024 * 1024):
            copied += len(chunk)
            if copied > limit:
                raise AppError("upload_too_large", "The upload exceeds the maximum archive size.", 413)
            sink.write(chunk)
    target.chmod(0o600)


@router.get("/{project_id}", response_model=ProjectDetails)
def get_project(request: Request, project_id: ProjectId) -> ProjectDetails:
    return _load(request, project_id).details


@router.delete("/{project_id}", status_code=204)
def delete_project(request: Request, project_id: ProjectId) -> Response:
    if not _store(request).delete(project_id):
        raise AppError("project_not_found", "This analysis does not exist or has expired.", 404)
    return Response(status_code=204)


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_stats(request: Request, project_id: ProjectId) -> ProjectStats:
    return _load(request, project_id).details.stats


@router.get("/{project_id}/tree", response_model=TreeResponse)
def get_tree(
    request: Request,
    project_id: ProjectId,
    node_id: Annotated[str | None, Query(alias="nodeId", max_length=64)] = None,
    depth: Annotated[int, Query(ge=0, le=MAX_TREE_DEPTH)] = 1,
    reveal: bool = False,
) -> TreeResponse:
    settings: Settings = request.app.state.settings
    index = _load(request, project_id).index
    target = node_id or index.root_id
    if index.get(target) is None:
        raise AppError("node_not_found", "That file or folder is not part of this analysis.", 404)
    tree = index.subtree(target, depth, reveal=reveal, max_nodes=settings.max_tree_response_nodes)
    if tree is None:
        raise AppError(
            "tree_too_large",
            f"That request would return more than {settings.max_tree_response_nodes:,} nodes. "
            "Ask for a smaller depth and expand folders individually.",
            422,
        )
    return TreeResponse(
        project_id=project_id, root_id=index.root_id, nodes=[to_api(node) for node in tree.nodes], children=tree.children
    )


@router.get("/{project_id}/search", response_model=SearchResponse)
def search(
    request: Request,
    project_id: ProjectId,
    q: Annotated[str, Query(max_length=200)] = "",
    extension: Annotated[list[str], Query(max_length=50)] = [],  # noqa: B006 - FastAPI copies defaults
    classification: Annotated[list[Classification], Query(max_length=10)] = [],  # noqa: B006
    type: Annotated[Literal["all", "file", "directory"], Query()] = "all",  # noqa: A002 - public query name
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = 500,
) -> SearchResponse:
    index = _load(request, project_id).index
    extensions = {_normalize_extension(value) for value in extension if value.strip()}
    result = index.search(q.strip(), extensions, set(classification), type, limit)
    return SearchResponse(
        project_id=project_id,
        root_id=index.root_id,
        nodes=[to_api(node) for node in result.nodes],
        children=result.children,
        match_ids=result.match_ids,
        total_matches=result.total_matches,
        truncated=result.truncated,
    )


def _normalize_extension(value: str) -> str:
    value = value.strip().lower()
    if value == NO_EXTENSION:
        return value
    return value if value.startswith(".") else f".{value}"
