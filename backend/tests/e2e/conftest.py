"""Starts a real uvicorn server serving the built frontend for Playwright tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from app.core.config import DEFAULT_FRONTEND_DIR
from tests.test_architecture import MONOREPO
from tests.zip_factory import SAMPLE_PROJECT, build_zip

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def server_url(tmp_path_factory) -> str:
    if not (DEFAULT_FRONTEND_DIR / "assets" / "app.css").exists():
        pytest.fail("Build the frontend CSS first: `make css`")
    port = _free_port()
    env = {
        **os.environ,
        "CODEATLAS_TEMP_DIR": str(tmp_path_factory.mktemp("e2e-work")),
        "CODEATLAS_MAX_UPLOAD_BYTES": str(24 * 1024 * 1024),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND_DIR,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        pytest.fail("CodeAtlas server did not start")
    yield url
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture(scope="session")
def archives(tmp_path_factory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("archives")
    files = {
        "sample": folder / "sample-app.zip",
        "corrupt": folder / "broken.zip",
        "traversal": folder / "evil.zip",
        "not_zip": folder / "notes.txt",
        "large": folder / "large.zip",
        "gitignore": folder / "with-gitignore.zip",
        "slow": folder / "many-files.zip",
        "built": folder / "built-app.zip",
        "huge": folder / "huge-100k.zip",
        "monorepo": folder / "shop-monorepo.zip",
    }
    files["sample"].write_bytes(build_zip(SAMPLE_PROJECT))
    files["corrupt"].write_bytes(b"PK\x03\x04" + os.urandom(2048))
    files["traversal"].write_bytes(build_zip([("ok.txt", "ok"), ("../escape.txt", "x")]))
    files["not_zip"].write_text("just text")
    files["large"].write_bytes(build_zip([("big/" + "x" * 10 + ".bin", os.urandom(25 * 1024 * 1024))]))
    files["gitignore"].write_bytes(
        build_zip([
            ("repo/.gitignore", "*.log\ndist/\n"),
            ("repo/src/app.py", "x"),
            ("repo/src/debug.log", "noise"),
            ("repo/dist/bundle.js", "y"),
            ("repo/docs/guide.md", "g"),
        ])
    )
    files["built"].write_bytes(
        build_zip([
            ("app/package.json", "{}"),
            ("app/src/main.ts", "x"),
            ("app/build/release.sh", "x"),
            ("app/dist/index.html", "<html>"),
            ("app/dist/assets/index-BK3j8d_a.js", "x"),
            ("app/dist/assets/index-BK3j8d_a.js.map", "x"),
        ])
    )
    # Enough files that analysis takes a few seconds, long enough to observe progress and cancel.
    files["slow"].write_bytes(build_zip([(f"many/d{i % 40}/f{i}.txt", "x") for i in range(18_000)]))
    files["monorepo"].write_bytes(build_zip(MONOREPO))
    # Same layout as scripts/benchmark.py: 100,000 files in ~3,250 folders.
    extensions = [".py", ".js", ".ts", ".md", ".json", ".css", ".html", ".go", ".java", ".yml"]
    files["huge"].write_bytes(
        build_zip([
            (f"repo/pkg{i % 50}/module{i % 400}/sub{i % 7}/file{i}{extensions[i % 10]}", f"// {i}\n")
            for i in range(100_000)
        ])
    )
    return files
