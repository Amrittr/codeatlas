"""Write demo archives to samples/ for trying CodeAtlas by hand.

- samples/sample-project.zip: the small multi-language fixture the test suite uses
- samples/codeatlas-source.zip: this repository's own source (dependencies left out)
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from tests.zip_factory import SAMPLE_PROJECT, build_zip  # noqa: E402

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "samples", "test-results", "e2e-screenshots"}


def write_self_archive(target: Path) -> int:
    count = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(REPO.rglob("*")):
            relative = path.relative_to(REPO)
            if any(part in SKIP_DIRS for part in relative.parts) or not path.is_file() or path.is_symlink():
                continue
            archive.write(path, Path("codeatlas") / relative)
            count += 1
    return count


def main() -> None:
    out = REPO / "samples"
    out.mkdir(exist_ok=True)
    (out / "sample-project.zip").write_bytes(build_zip(SAMPLE_PROJECT))
    files = write_self_archive(out / "codeatlas-source.zip")
    print(f"Wrote {out / 'sample-project.zip'}")
    print(f"Wrote {out / 'codeatlas-source.zip'} ({files} files)")


if __name__ == "__main__":
    main()
