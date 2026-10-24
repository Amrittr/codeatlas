"""Background analysis jobs: lifecycle, progress, cancellation, queue limits and cleanup."""

from __future__ import annotations

import threading
import time

import pytest

from app.services import job_service
from app.services.analysis_context import AnalysisContext
from tests.conftest import wait_for_job
from tests.zip_factory import SAMPLE_PROJECT, build_zip


def submit(client, data: bytes, **form):
    return client.post("/api/projects/analyze", files={"file": ("p.zip", data, "application/zip")}, data=form)


@pytest.fixture
def blocking_analysis(monkeypatch):
    """Replace the analysis with one that waits until released, checking for cancellation."""
    release = threading.Event()
    started = threading.Event()

    def fake_analyze(archive_path, extract_dir, file_name, settings, options, context: AnalysisContext):
        context.set_phase("extracting", total=10)
        started.set()
        while not release.is_set():
            context.checkpoint()
            time.sleep(0.005)
        raise RuntimeError("released")  # tests only release jobs they expect to fail or cancel

    monkeypatch.setattr(job_service, "analyze_archive", fake_analyze)
    yield started, release
    release.set()


def test_analyze_returns_202_and_job_completes(client):
    response = submit(client, build_zip(SAMPLE_PROJECT))
    assert response.status_code == 202
    job = response.json()["job"]
    assert set(job) == {"id", "status", "fileName", "createdAt", "progress", "projectId", "error"}
    assert job["status"] in ("queued", "running", "completed")

    final = wait_for_job(client, job["id"])
    assert final["status"] == "completed"
    assert final["progress"]["phase"] == "done"
    assert final["error"] is None
    assert client.get(f"/api/projects/{final['projectId']}").status_code == 200


def test_failed_job_reports_error_and_cleans_up(client, temp_root):
    response = submit(client, build_zip([("../evil.txt", "x")]))
    assert response.status_code == 202  # structure is fine; the unsafe name is found during planning
    job = wait_for_job(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert job["error"] == {
        "code": "unsafe_archive",
        "message": job["error"]["message"],
        "statusCode": 400,
    }
    assert job["projectId"] is None
    assert list(temp_root.iterdir()) == []


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"not a zip at all", 415, "unsupported_file_type"),
        (b"PK\x03\x04garbage-without-central-directory", 400, "invalid_archive"),
        (b"", 400, "invalid_archive"),
    ],
)
def test_structural_problems_fail_synchronously(client, temp_root, data, status, code):
    response = submit(client, data)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert list(temp_root.iterdir()) == []


def test_cancel_running_job(make_client, blocking_analysis, temp_root):
    started, _ = blocking_analysis
    client = make_client()
    job_id = submit(client, build_zip([("a.txt", "a")])).json()["job"]["id"]
    assert started.wait(5)
    running = client.get(f"/api/jobs/{job_id}").json()["job"]
    assert running["status"] == "running"
    assert running["progress"] == {"phase": "extracting", "current": 0, "total": 10, "unit": "files"}

    response = client.delete(f"/api/jobs/{job_id}")
    assert response.status_code == 202
    assert wait_for_job(client, job_id)["status"] == "cancelled"
    assert list(temp_root.iterdir()) == []


def test_cancel_queued_job_and_queue_limit(make_client, blocking_analysis, temp_root):
    started, _ = blocking_analysis
    client = make_client(max_concurrent_analyses=1, max_queued_jobs=1)
    first = submit(client, build_zip([("a.txt", "a")])).json()["job"]["id"]
    assert started.wait(5)
    second = submit(client, build_zip([("b.txt", "b")])).json()["job"]["id"]
    assert client.get(f"/api/jobs/{second}").json()["job"]["status"] == "queued"

    busy = submit(client, build_zip([("c.txt", "c")]))
    assert busy.status_code == 503
    assert busy.json()["error"]["code"] == "server_busy"

    assert client.delete(f"/api/jobs/{second}").json()["job"]["status"] == "cancelled"
    client.delete(f"/api/jobs/{first}")
    assert wait_for_job(client, first)["status"] == "cancelled"
    assert list(temp_root.iterdir()) == []


def test_cancel_finished_job_is_a_no_op(client):
    job_id = submit(client, build_zip([("a.txt", "a")])).json()["job"]["id"]
    assert wait_for_job(client, job_id)["status"] == "completed"
    assert client.delete(f"/api/jobs/{job_id}").json()["job"]["status"] == "completed"


def test_unexpected_crash_becomes_failed_job(client, monkeypatch, temp_root):
    def crash(*args, **kwargs):
        raise KeyError("boom")

    monkeypatch.setattr(job_service, "analyze_archive", crash)
    job_id = submit(client, build_zip([("a.txt", "a")])).json()["job"]["id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "internal_error"
    assert "boom" not in job["error"]["message"]
    assert list(temp_root.iterdir()) == []


def test_timeout_inside_job(make_client, upload):
    client = make_client(max_analysis_seconds=0.000001)
    response = upload(build_zip([(f"p/f{i}.txt", "x") for i in range(50)]), test_client=client)
    assert response.status_code == 408
    assert response.json()["error"]["code"] == "analysis_timeout"


def test_progress_reports_real_counts(client):
    job_id = submit(client, build_zip([(f"p/f{i}.txt", "x") for i in range(30)])).json()["job"]["id"]
    seen = set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()["job"]
        progress = job["progress"]
        if progress["total"] is not None:
            assert 0 <= progress["current"] <= progress["total"]
        seen.add(progress["phase"])
        if job["status"] == "completed":
            break
    assert "done" in seen


def test_unknown_and_malformed_job_ids(client):
    assert client.get(f"/api/jobs/{'0' * 32}").json()["error"]["code"] == "job_not_found"
    assert client.delete(f"/api/jobs/{'0' * 32}").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 422


def test_finished_job_records_expire(make_client, monkeypatch):
    client = make_client(job_ttl_seconds=1)
    manager = client.app.state.jobs
    job_id = submit(client, build_zip([("a.txt", "a")])).json()["job"]["id"]
    wait_for_job(client, job_id)
    real_clock = manager._clock
    monkeypatch.setattr(manager, "_clock", lambda: real_clock() + 5)
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_shutdown_cancels_running_jobs(make_client, blocking_analysis, temp_root):
    started, _ = blocking_analysis
    client = make_client()
    job_id = submit(client, build_zip([("a.txt", "a")])).json()["job"]["id"]
    assert started.wait(5)
    manager = client.app.state.jobs
    manager.shutdown()
    assert manager.get(job_id).status.value == "cancelled"
    assert list(temp_root.iterdir()) == []
