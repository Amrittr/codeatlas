"""Measure analysis time, memory and response sizes for synthetic projects of different sizes.

Usage: backend/.venv/bin/python scripts/benchmark.py [file counts...]   (default: 1000 10000 20000 50000 100000)

Each size runs in a fresh subprocess, so peak RSS belongs to that size alone. Limits are
raised inside the benchmark (``MAX_FILES`` etc.) so sizes above the shipped defaults can be
measured. Results depend on hardware; record the machine alongside the numbers in docs/TESTING.md.
"""

from __future__ import annotations

import gc
import io
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
import tracemalloc
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

EXTENSIONS = [".py", ".js", ".ts", ".md", ".json", ".css", ".html", ".go", ".java", ".yml"]
DEFAULT_COUNTS = [1_000, 10_000, 20_000, 50_000, 100_000]


def synthetic_zip(file_count: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index in range(file_count):
            folder = f"repo/pkg{index % 50}/module{index % 400}/sub{index % 7}"
            archive.writestr(f"{folder}/file{index}{EXTENSIONS[index % len(EXTENSIONS)]}", f"// {index}\n" * 3)
    return buffer.getvalue()


def peak_rss_bytes() -> int:
    # ru_maxrss is bytes on macOS and kilobytes on Linux.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def analyze(client, data: bytes) -> tuple[dict, float]:
    started = time.perf_counter()
    response = client.post("/api/projects/analyze", files={"file": ("repo.zip", data, "application/zip")})
    response.raise_for_status()
    job_id = response.json()["job"]["id"]
    while (job := client.get(f"/api/jobs/{job_id}").json()["job"])["status"] in ("queued", "running"):
        time.sleep(0.02)
    if job["status"] != "completed":
        raise SystemExit(f"analysis {job['status']}: {job['error']}")
    elapsed = time.perf_counter() - started
    return client.get(f"/api/projects/{job['projectId']}").json(), elapsed


def run_single(file_count: int) -> dict:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    data = synthetic_zip(file_count)
    with tempfile.TemporaryDirectory() as temp_dir:
        settings = Settings(
            _env_file=None,
            temp_dir=Path(temp_dir),
            serve_frontend=False,
            max_files=max(file_count, 20_000),
            max_directories=max(file_count, 20_000),
            max_analysis_seconds=1800,
        )
        client = TestClient(create_app(settings))
        baseline_rss = peak_rss_bytes()
        details, elapsed = analyze(client, data)
        project_id = details["project"]["id"]
        result = {
            "files": file_count,
            "archive_mb": len(data) / 1e6,
            "nodes": details["project"]["nodeCount"],
            "analyze_s": elapsed,
            "extract_s": details["project"]["durations"]["extractMs"] / 1000,
            "scan_s": details["project"]["durations"]["scanMs"] / 1000,
            "peak_rss_mb": peak_rss_bytes() / 1e6,
            "baseline_rss_mb": baseline_rss / 1e6,
            "queries": {},
        }
        for label, path, params in [
            ("tree depth=2", f"/api/projects/{project_id}/tree", {"depth": 2}),
            ("tree full", f"/api/projects/{project_id}/tree", {"depth": 1024}),
            ("search 'file1'", f"/api/projects/{project_id}/search", {"q": "file1"}),
            ("search .py", f"/api/projects/{project_id}/search", {"extension": ".py"}),
            ("search miss", f"/api/projects/{project_id}/search", {"q": "zzz-no-match"}),
        ]:
            timings = []
            for _ in range(3):
                t0 = time.perf_counter()
                response = client.get(path, params=params)
                timings.append(time.perf_counter() - t0)
            result["queries"][label] = {"ms": min(timings) * 1000, "kb": len(response.content) / 1e3}

        # Retained memory of one stored analysis, measured on a second, traced run.
        client.delete(f"/api/projects/{project_id}")
        gc.collect()
        tracemalloc.start()
        before = tracemalloc.get_traced_memory()[0]
        details, _ = analyze(client, data)
        gc.collect()
        retained = tracemalloc.get_traced_memory()[0] - before
        tracemalloc.stop()
        result["retained_mb"] = retained / 1e6
        result["bytes_per_node"] = retained / details["project"]["nodeCount"]
        client.app.state.jobs.shutdown()
    return result


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--single":
        print(json.dumps(run_single(int(sys.argv[2]))))
        return
    counts = [int(arg) for arg in sys.argv[1:]] or DEFAULT_COUNTS
    print(f"Python {platform.python_version()} · {platform.machine()} · {os.cpu_count()} CPUs · {platform.platform()}")
    for count in counts:
        output = subprocess.run(
            [sys.executable, "-W", "ignore", __file__, "--single", str(count)],
            capture_output=True, text=True, check=True,
        ).stdout
        result = json.loads(output.strip().splitlines()[-1])
        print(
            f"\n{result['files']:,} files · archive {result['archive_mb']:.1f} MB · {result['nodes']:,} nodes\n"
            f"  analyze {result['analyze_s']:.2f} s (extract {result['extract_s']:.2f} s, scan {result['scan_s']:.2f} s)"
            f" · peak RSS {result['peak_rss_mb']:.0f} MB (baseline {result['baseline_rss_mb']:.0f})"
            f" · retained {result['retained_mb']:.1f} MB ({result['bytes_per_node']:.0f} B/node)"
        )
        for label, query in result["queries"].items():
            print(f"  {label:<16} {query['ms']:8.1f} ms · {query['kb']:10.1f} KB")


if __name__ == "__main__":
    main()
