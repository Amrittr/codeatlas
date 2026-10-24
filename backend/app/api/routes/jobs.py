from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.core.errors import AppError
from app.schemas.project import JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", description="Id returned by POST /api/projects/analyze")]


def _not_found() -> AppError:
    return AppError("job_not_found", "This analysis job does not exist or its record has expired.", 404)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(request: Request, job_id: JobId) -> JobResponse:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise _not_found()
    return JobResponse(job=job.view())


@router.delete("/{job_id}", response_model=JobResponse, status_code=202)
def cancel_job(request: Request, job_id: JobId) -> JobResponse:
    """Request cancellation. A finished job is returned unchanged."""
    job = request.app.state.jobs.cancel(job_id)
    if job is None:
        raise _not_found()
    return JobResponse(job=job.view())
