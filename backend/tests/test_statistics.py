"""Statistics must be derived from the scanned project, verified against a hand-counted fixture."""

from __future__ import annotations

from tests.zip_factory import SAMPLE_PROJECT, Entry, build_zip

ANALYZED = [
    entry for entry in SAMPLE_PROJECT
    if isinstance(entry, tuple) and "/node_modules/" not in entry[0] and "/.git/" not in entry[0]
]


def test_sample_project_statistics(upload):
    stats = upload(build_zip(SAMPLE_PROJECT)).json()["stats"]

    assert stats["totalFiles"] == len(ANALYZED) == 22
    assert stats["totalDirectories"] == 12  # analyzed folders; node_modules and .git are excluded
    assert stats["excludedDirectoryCount"] == 2
    assert stats["excludedFileCount"] == 0
    assert stats["excludedEntryCount"] == 3
    assert stats["totalSizeBytes"] == sum(len(data.encode()) for _, data in ANALYZED)
    assert stats["hiddenFileCount"] == 2
    assert stats["maxDepth"] == 4

    extensions = {item["extension"]: item["fileCount"] for item in stats["extensions"]}
    assert extensions == {
        ".js": 4, ".py": 4, "(none)": 4, ".md": 3, ".json": 1, ".ts": 1, ".css": 1, ".jsx": 1,
        ".svg": 1, ".csv": 1, ".example": 1,
    }
    assert stats["fileTypeCount"] == len(extensions)
    assert sum(item["fileCount"] for item in stats["extensions"]) == stats["totalFiles"]

    classifications = {item["classification"]: item["fileCount"] for item in stats["classifications"]}
    assert classifications == {"source": 9, "config": 5, "documentation": 4, "test": 2, "asset": 1, "data": 1}
    assert stats["sourceFileCount"] == 9
    assert stats["testFileCount"] == 2
    assert stats["configFileCount"] == 5
    assert stats["documentationFileCount"] == 4

    languages = {item["language"]: item["fileCount"] for item in stats["languages"]}
    assert languages["JavaScript"] == 5
    assert languages["Python"] == 4

    config_paths = [item["path"] for item in stats["configFiles"]]
    assert "sample-app/package.json" in config_paths
    assert "sample-app/Dockerfile" in config_paths


def test_largest_files_are_ordered(upload):
    data = build_zip([("p/small.txt", "a"), ("p/big.txt", "a" * 300), ("p/mid.txt", "a" * 20)])
    largest = upload(data).json()["stats"]["largestFiles"]
    assert [item["path"] for item in largest] == ["p/big.txt", "p/mid.txt", "p/small.txt"]


def test_statistics_endpoint_matches_analyze_response(upload, client):
    body = upload(build_zip(SAMPLE_PROJECT)).json()
    stats = client.get(f"/api/projects/{body['project']['id']}/stats").json()
    assert stats == body["stats"]


def test_env_file_triggers_secret_warning_without_reading_it(upload):
    body = upload(build_zip([("p/.env", "API_KEY=super-secret-value"), Entry("p/a.py", b"x")])).json()
    assert any(warning["code"] == "possible_secrets" for warning in body["warnings"])
    assert "super-secret-value" not in str(body)
