"""Structure accuracy: the tree must match exactly what the archive contains."""

from __future__ import annotations

import os

import pytest

from app.services.analysis_context import AnalysisContext
from app.services.scan_service import ROOT_ID, node_id, scan_directory
from tests.zip_factory import SAMPLE_PROJECT, build_zip


@pytest.fixture
def sample(upload, client):
    body = upload(build_zip(SAMPLE_PROJECT), name="sample-app.zip").json()
    project_id = body["project"]["id"]
    tree = client.get(f"/api/projects/{project_id}/tree", params={"depth": 64}).json()
    nodes = {node["path"]: node for node in tree["nodes"]}
    return body, tree, nodes


def names(tree, nodes, path):
    return [next(n["name"] for n in tree["nodes"] if n["id"] == child) for child in tree["children"][nodes[path]["id"]]]


def test_project_name_comes_from_single_top_folder(sample):
    body, _, _ = sample
    assert body["project"]["name"] == "sample-app"


def test_children_sorted_folders_first_then_name(sample):
    _, tree, nodes = sample
    assert names(tree, nodes, "sample-app") == [
        ".git", "assets", "data", "docs", "empty-folder", "node_modules", "server", "src", "tests",
        ".env.example", ".gitignore", "Dockerfile", "LICENSE", "Makefile", "package.json", "README.md",
    ]


def test_nested_directories_and_counts(sample):
    _, tree, nodes = sample
    src = nodes["sample-app/src"]
    assert src["childCount"] == 5
    assert src["descendantFileCount"] == 6
    assert src["descendantDirectoryCount"] == 3
    assert nodes["sample-app/src/components/Button.jsx"]["depth"] == 4
    assert names(tree, nodes, "sample-app/src/components") == ["Button.jsx", "index.js"]


def test_aggregate_size_matches_files(sample):
    _, tree, nodes = sample
    expected = sum(n["sizeBytes"] for n in tree["nodes"] if n["type"] == "file" and n["path"].startswith("sample-app/src/"))
    assert nodes["sample-app/src"]["sizeBytes"] == expected
    assert nodes["sample-app/src/App.js"]["sizeBytes"] == len("export const App = () => null;\n")


def test_duplicate_basenames_have_distinct_ids(sample):
    _, _, nodes = sample
    first, second = nodes["sample-app/src/index.js"], nodes["sample-app/src/components/index.js"]
    assert first["id"] != second["id"]
    assert first["parentId"] == nodes["sample-app/src"]["id"]
    assert second["parentId"] == nodes["sample-app/src/components"]["id"]


def test_files_without_extensions(sample):
    _, _, nodes = sample
    for path in ("sample-app/LICENSE", "sample-app/Makefile", "sample-app/Dockerfile"):
        assert nodes[path]["extension"] == ""


def test_hidden_files_are_included_and_flagged(sample):
    _, _, nodes = sample
    assert nodes["sample-app/.gitignore"]["hidden"] is True
    assert nodes["sample-app/README.md"]["hidden"] is False


def test_unicode_filenames(sample):
    _, _, nodes = sample
    assert nodes["sample-app/docs/über-café.md"]["name"] == "über-café.md"


def test_empty_directories_are_kept(sample):
    body, _, nodes = sample
    assert nodes["sample-app/empty-folder"]["childCount"] == 0
    assert body["stats"]["emptyDirectoryCount"] == 1


def test_default_exclusions_are_visible_with_counts(sample):
    body, tree, nodes = sample
    node_modules = nodes["sample-app/node_modules"]
    assert node_modules["excluded"] is True
    assert node_modules["excludedReason"] == "dependencies"
    assert node_modules["excludedEntryCount"] == 2
    assert tree["children"][node_modules["id"]] == []
    exclusions = {item["path"]: item for item in body["exclusions"]}
    assert exclusions["sample-app/.git"]["reason"] == "version_control"
    assert exclusions["sample-app/.git"]["entryCount"] == 1
    assert not any(path.startswith("sample-app/node_modules/") for path in nodes)


def test_modified_time_comes_from_archive(sample):
    _, _, nodes = sample
    assert nodes["sample-app/README.md"]["modifiedAt"] == "2024-05-17T12:30:00"


def test_exclusions_can_be_disabled(upload):
    body = upload(build_zip(SAMPLE_PROJECT), applyDefaultExclusions=False, respectGitignore=False).json()
    assert body["exclusions"] == []
    assert body["stats"]["totalFiles"] == 25
    assert body["project"]["exclusionSettings"]["defaultRules"] is False
    assert body["project"]["exclusionSettings"]["gitignore"] is False


def test_gitignore_still_applies_when_default_rules_are_off(upload):
    """The fixture's own .gitignore lists node_modules/, so it stays excluded, attributed to .gitignore."""
    body = upload(build_zip(SAMPLE_PROJECT), applyDefaultExclusions=False).json()
    exclusions = {item["path"]: item for item in body["exclusions"]}
    assert exclusions["sample-app/node_modules"]["reason"] == "gitignore"
    assert exclusions["sample-app/node_modules"]["rule"] == "sample-app/.gitignore line 1: node_modules/"
    assert "sample-app/.git" not in exclusions
    assert body["project"]["exclusionSettings"]["gitignoreFiles"] == ["sample-app/.gitignore"]


def test_macos_metadata_is_always_excluded(upload):
    data = build_zip([("p/a.txt", "a"), ("__MACOSX/p/._a.txt", "meta")])
    body = upload(data, applyDefaultExclusions=False).json()
    assert body["exclusions"] == [
        {
            "nodeId": node_id("__MACOSX"),
            "path": "__MACOSX",
            "type": "directory",
            "reason": "archive_metadata",
            "rule": "always excluded: __MACOSX/",
            "entryCount": 1,
        }
    ]


def test_empty_archive(upload):
    body = upload(build_zip([])).json()
    assert body["stats"]["totalFiles"] == 0
    assert body["stats"]["totalDirectories"] == 0
    assert body["warnings"][0]["code"] == "empty_project"
    assert body["project"]["nodeCount"] == 1


def test_archive_with_only_directories(upload):
    body = upload(build_zip(["a/", "a/b/", "c/"])).json()
    assert body["stats"]["totalFiles"] == 0
    assert body["stats"]["totalDirectories"] == 3
    assert body["stats"]["emptyDirectoryCount"] == 2


def test_implicit_parent_directories_are_created(upload, client):
    body = upload(build_zip([("x/y/z/file.txt", "1")])).json()
    assert body["stats"]["totalDirectories"] == 3


def test_ids_are_stable_across_analyses(upload, client):
    data = build_zip(SAMPLE_PROJECT)
    first = upload(data).json()["project"]["id"]
    second = upload(data).json()["project"]["id"]
    assert first != second
    tree_a = client.get(f"/api/projects/{first}/tree", params={"depth": 64}).json()
    tree_b = client.get(f"/api/projects/{second}/tree", params={"depth": 64}).json()
    assert tree_a["nodes"] == tree_b["nodes"]


def test_scanner_reports_but_does_not_follow_symlinks(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    os.symlink(outside, root / "linked")

    result = scan_directory(root, root_name="proj", context=AnalysisContext.started(10), max_files=100, max_depth=10)
    assert ("linked", "symlink_not_followed") in result.skipped
    assert all("secret" not in node.path for node in result.nodes.values())
    assert result.nodes[ROOT_ID].descendant_file_count == 1


def test_children_use_natural_order(upload, client):
    body = upload(build_zip([("p/module10/a.py", "x"), ("p/module2/a.py", "x"), ("p/Module1/a.py", "x"), ("p/file10.txt", "x"), ("p/file9.txt", "x")])).json()
    tree = client.get(f"/api/projects/{body['project']['id']}/tree", params={"depth": 2}).json()
    by_id = {node["id"]: node for node in tree["nodes"]}
    p_id = next(node["id"] for node in tree["nodes"] if node["path"] == "p")
    assert [by_id[child]["name"] for child in tree["children"][p_id]] == ["Module1", "module2", "module10", "file9.txt", "file10.txt"]
