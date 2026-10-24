"""Background analysis jobs.

The upload request saves the archive into a private work directory, runs the cheap
structural checks, and hands the directory to a job. The job runs in a bounded thread pool
and owns the work directory, which is removed when the job ends, whether it completes,
fails or is cancelled.

Cancellation sets a flag that the analysis observes at its next checkpoint (between archive
entries, extracted files and scanned folders). A job that has not started yet is cancelled
immediately.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.repositories.project_store import ProjectStore
from app.schemas.project import JobError, JobProgress, JobStatus, JobView
from app.services.analysis_context import AnalysisCancelled, AnalysisContext
from app.services.analysis_service import AnalysisOptions, analyze_archive, remove_workdir

logger = logging.getLogger("codeatlas.jobs")

ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


@dataclass
class Job:
    id: str
    file_name: str
    workdir: Path
    archive_path: Path
    options: AnalysisOptions
    context: AnalysisContext
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: JobStatus = JobStatus.QUEUED
    project_id: str | None = None
    error: AppError | None = None
    finished_at: float | None = None
    future: Future | None = None

    def view(self) -> JobView:
        progress = self.context.snapshot()
        return JobView(
            id=self.id,
            status=self.status,
            file_name=self.file_name,
            created_at=self.created_at,
            progress=JobProgress(phase=progress.phase, current=progress.current, total=progress.total, unit=progress.unit),
            project_id=self.project_id,
            error=JobError(code=self.error.code, message=self.error.message, status_code=self.error.status_code)
            if self.error
            else None,
        )


class JobManager:
    def __init__(self, settings: Settings, store: ProjectStore, clock=time.monotonic) -> None:
        self._settings = settings
        self._store = store
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_analyses, thread_name_prefix="codeatlas-analysis"
        )

    def submit(self, workdir: Path, archive_path: Path, file_name: str, options: AnalysisOptions) -> Job:
        """Queue an analysis. Raises ``server_busy`` when the queue is full; the caller then owns cleanup."""
        with self._lock:
            self._purge_finished()
            active = sum(1 for job in self._jobs.values() if job.status in ACTIVE)
            if active >= self._settings.max_concurrent_analyses + self._settings.max_queued_jobs:
                raise AppError("server_busy", "The server is already analyzing other uploads. Try again shortly.", 503)
            job = Job(
                id=uuid.uuid4().hex,
                file_name=file_name,
                workdir=workdir,
                archive_path=archive_path,
                options=options,
                context=AnalysisContext(self._settings.max_analysis_seconds),
            )
            self._jobs[job.id] = job
            job.future = self._executor.submit(self._run, job)
        logger.info("Queued analysis job %s", job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._purge_finished()
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in ACTIVE:
                return job
            job.context.cancel()
            never_started = job.status == JobStatus.QUEUED and job.future is not None and job.future.cancel()
            if never_started:
                self._finish(job, JobStatus.CANCELLED)
        if never_started:
            remove_workdir(job.workdir)
        return job

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.context.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            leftovers = [job for job in self._jobs.values() if job.status in ACTIVE]
            for job in leftovers:
                self._finish(job, JobStatus.CANCELLED)
        for job in leftovers:
            remove_workdir(job.workdir)

    def _run(self, job: Job) -> None:
        with self._lock:
            if job.context.cancel_requested:
                self._finish(job, JobStatus.CANCELLED)
                cancelled_before_start = True
            else:
                job.status = JobStatus.RUNNING
                cancelled_before_start = False
        if cancelled_before_start:
            remove_workdir(job.workdir)
            return
        job.context.start()
        try:
            details, index = analyze_archive(
                job.archive_path,
                job.workdir / "project",
                job.file_name,
                self._settings,
                job.options,
                job.context,
            )
        except AnalysisCancelled:
            outcome, error = JobStatus.CANCELLED, None
        except AppError as app_error:
            outcome, error = JobStatus.FAILED, app_error
        except Exception as unexpected:  # noqa: BLE001 - a job must always reach a final state
            logger.error(
                "Analysis job %s crashed with %s",
                job.id,
                type(unexpected).__name__,
                exc_info=unexpected if not self._settings.is_production else None,
            )
            outcome, error = JobStatus.FAILED, AppError("internal_error", "Unexpected server error during analysis.", 500)
        else:
            outcome, error = JobStatus.COMPLETED, None
        # Delete the archive and extracted files before the job reports a final state.
        remove_workdir(job.workdir)
        if outcome == JobStatus.COMPLETED:
            self._store.put(details, index)
            job.project_id = details.project.id
            job.context.set_phase("done")
        with self._lock:
            job.error = error
            self._finish(job, outcome)
        logger.info("Analysis job %s finished: %s", job.id, outcome.value)

    def _finish(self, job: Job, status: JobStatus) -> None:
        """Record the final state. Call under the lock; remove the work directory outside it."""
        job.status = status
        job.finished_at = self._clock()

    def _purge_finished(self) -> None:
        cutoff = self._clock() - self._settings.job_ttl_seconds
        for job_id in [key for key, job in self._jobs.items() if job.finished_at is not None and job.finished_at < cutoff]:
            del self._jobs[job_id]
