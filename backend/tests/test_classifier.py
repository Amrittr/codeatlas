from __future__ import annotations

import pytest

from app.analyzers.classifier import classify
from app.analyzers.config_detector import detect_config
from app.analyzers.language_detector import detect_language
from app.services.scan_service import split_extension


def run(path: str):
    parts = tuple(path.split("/"))
    name = parts[-1]
    extension = split_extension(name)
    return classify(name, extension, parts[:-1], detect_language(name, extension), detect_config(name, path))


@pytest.mark.parametrize(
    ("path", "classification", "confidence"),
    [
        ("src/app.py", "source", "high"),
        ("web/index.html", "source", "high"),
        ("web/theme.scss", "source", "high"),
        ("tests/test_app.py", "test", "high"),
        ("src/app_test.go", "test", "high"),
        ("src/Button.test.tsx", "test", "high"),
        ("src/api.spec.js", "test", "high"),
        ("src/test/java/com/acme/UserServiceTest.java", "test", "high"),
        ("tests/helpers.py", "test", "medium"),
        ("tests/fixtures/data.json", "data", "medium"),
        ("tests/conftest.py", "config", "high"),
        ("package.json", "config", "high"),
        ("pyproject.toml", "config", "high"),
        ("requirements-dev.txt", "config", "high"),
        (".github/workflows/ci.yml", "config", "high"),
        ("config/settings.yaml", "config", "medium"),
        ("Dockerfile", "config", "high"),
        (".env", "config", "high"),
        ("README.md", "documentation", "high"),
        ("LICENSE", "documentation", "high"),
        ("docs/architecture.md", "documentation", "high"),
        ("docs/NOTES", "documentation", "medium"),
        ("package-lock.json", "generated", "high"),
        ("static/app.min.js", "generated", "high"),
        ("dist/bundle.js", "source", "high"),  # folder-level evidence is generated_detector's job
        ("static/js/main.3f9a2c1b.js", "generated", "high"),
        ("assets/index-BK3j8d_a.js", "generated", "high"),
        ("db/migration-20240101.js", "source", "high"),
        ("proto/user_pb2.py", "generated", "high"),
        ("src/api.generated.ts", "generated", "high"),
        ("lib/native.so", "generated", "high"),
        ("public/logo.png", "asset", "high"),
        ("fonts/Inter.woff2", "asset", "high"),
        ("data/users.csv", "data", "medium"),
        ("data/raw.parquet", "data", "medium"),
        ("notes.txt", "documentation", "low"),
        ("bin/tool", "other", "low"),
        ("weird.xyz", "other", "low"),
    ],
)
def test_classification(path, classification, confidence):
    result = run(path)
    assert (result.classification.value, result.confidence.value) == (classification, confidence)
    assert result.reason


@pytest.mark.parametrize(
    ("name", "language"),
    [
        ("main.ts", "TypeScript"),
        ("App.JSX", "JavaScript"),
        ("Makefile", "Makefile"),
        ("Dockerfile.prod", "Dockerfile"),
        ("CMakeLists.txt", "CMake"),
        ("lib.rs", "Rust"),
        ("notes.unknownext", None),
        ("LICENSE", None),
    ],
)
def test_language_detection(name, language):
    detected = detect_language(name, split_extension(name))
    assert (detected.name if detected else None) == language


def test_config_detection_labels():
    assert detect_config("tsconfig.build.json", "tsconfig.build.json").label == "TypeScript compiler config"
    assert detect_config("ci.yml", ".github/workflows/ci.yml").category == "ci"
    assert detect_config("ci.yml", "other/ci.yml") is None
