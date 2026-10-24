from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TERMINAL = {"completed", "failed", "cancelled"}


@pytest.fixture
def temp_root(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    root.mkdir()
    return root


@pytest.fixture
def make_settings(temp_root: Path) -> Callable[..., Settings]:
    def factory(**overrides) -> Settings:
        values = {"temp_dir": temp_root, "serve_frontend": False, **overrides}
        return Settings(_env_file=None, **values)

    return factory


@pytest.fixture
def make_client(make_settings) -> Callable[..., TestClient]:
    clients: list[TestClient] = []

    def factory(**overrides) -> TestClient:
        client = TestClient(create_app(make_settings(**overrides)))
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.app.state.jobs.shutdown()


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()["job"]
        if job["status"] in TERMINAL:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


class Outcome:
    """The final result of upload + background job, shaped like an HTTP response.

    A completed job becomes 201 with the project details; a failed one carries the job's
    error status and body, exactly as the API reports them.
    """

    def __init__(self, status_code: int, body: dict, job: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body
        self.job = job

    def json(self) -> dict:
        return self._body


def _form_value(value) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


@pytest.fixture
def upload(client: TestClient):
    """POST a ZIP, wait for its analysis job, and return the outcome."""

    def do_upload(data: bytes, name: str = "project.zip", test_client: TestClient | None = None, **form):
        target = test_client or client
        response = target.post(
            "/api/projects/analyze",
            files={"file": (name, data, "application/zip")},
            data={key: _form_value(value) for key, value in form.items()},
        )
        if response.status_code != 202:
            return response
        job = wait_for_job(target, response.json()["job"]["id"])
        if job["status"] == "completed":
            return Outcome(201, target.get(f"/api/projects/{job['projectId']}").json(), job)
        if job["status"] == "failed":
            error = job["error"]
            return Outcome(error["statusCode"], {"error": {"code": error["code"], "message": error["message"]}}, job)
        return Outcome(499, {"error": {"code": "cancelled", "message": "cancelled"}}, job)

    return do_upload
