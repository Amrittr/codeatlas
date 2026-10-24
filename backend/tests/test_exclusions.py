"""Exclusion policy: .gitignore semantics, custom rules, ordering, and visibility in results."""

from __future__ import annotations

import pytest

from app.analyzers.exclusions import MAX_GITIGNORE_BYTES, ExclusionPolicy, PatternError, parse_pattern_text
from app.services.analysis_context import AnalysisContext
from app.services.scan_service import scan_directory
from tests.zip_factory import build_zip


def decide(policy: ExclusionPolicy, path: str, is_directory: bool = False):
    result = policy.first_excluded(tuple(path.split("/")), is_directory)
    return None if result is None else (result[0], result[1].reason, result[1].rule)


# ---------- policy unit tests ----------


def test_gitignore_basic_negation_and_line_numbers():
    policy = ExclusionPolicy()
    policy.add_gitignore((), "# comment\n*.log\n!keep.log\nbuild/\n/root-only.txt\n")
    assert decide(policy, "app.log") == (0, "gitignore", ".gitignore line 2: *.log")
    assert decide(policy, "src/deep/app.log")[1] == "gitignore"
    assert decide(policy, "keep.log") is None
    assert decide(policy, "src/build/out.js") == (1, "gitignore", ".gitignore line 4: build/")
    assert decide(policy, "build") is None  # "build/" matches directories only
    assert decide(policy, "root-only.txt")[1] == "gitignore"
    assert decide(policy, "src/root-only.txt") is None  # anchored to the .gitignore's folder


def test_nested_gitignore_applies_to_its_folder_and_overrides_parent():
    policy = ExclusionPolicy()
    policy.add_gitignore((), "*.tmp\n")
    policy.add_gitignore(("pkg",), "!important.tmp\n/generated/\n")
    assert decide(policy, "pkg/important.tmp") is None
    assert decide(policy, "other/important.tmp")[1] == "gitignore"
    assert decide(policy, "pkg/generated/x.py") == (1, "gitignore", "pkg/.gitignore line 2: /generated/")
    assert decide(policy, "generated/x.py") is None  # the nested rule does not apply outside pkg/


def test_cannot_reinclude_file_inside_excluded_folder():
    policy = ExclusionPolicy()
    policy.add_gitignore((), "logs/\n!logs/keep.txt\n")
    assert decide(policy, "logs/keep.txt") == (0, "gitignore", ".gitignore line 1: logs/")


def test_rule_order_include_beats_everything_but_archive_metadata():
    policy = ExclusionPolicy(include_patterns=["node_modules/", "__MACOSX/"], exclude_patterns=["docs/", "*.bak"])
    policy.add_gitignore((), "docs/\nnode_modules/\n")
    assert decide(policy, "node_modules/x/index.js") is None
    assert decide(policy, "__MACOSX/a", True)[1] == "archive_metadata"
    assert decide(policy, "docs/guide.md") == (0, "custom", "custom rule: docs/")
    assert decide(policy, "src/old.bak") == (1, "custom", "custom rule: *.bak")


def test_default_rules_and_toggles():
    assert decide(ExclusionPolicy(), "a/.venv/lib/x.py") == (1, "virtual_environment", "default rule: .venv/")
    assert decide(ExclusionPolicy(apply_default_rules=False), "a/.venv/lib/x.py") is None
    policy = ExclusionPolicy(respect_gitignore=False)
    policy.add_gitignore((), "*.log\n")
    assert decide(policy, "a.log") is None


def test_default_rules_only_match_folders():
    assert decide(ExclusionPolicy(), "notes/node_modules") is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("\n".join(f"p{i}" for i in range(101)), "at most 100"),
        ("x" * 257, "longer than 256"),
    ],
)
def test_pattern_limits(text, message):
    with pytest.raises(PatternError, match=message):
        parse_pattern_text(text, label="Exclude patterns")


def test_pattern_text_ignores_blanks_and_comments():
    assert parse_pattern_text("  dist/ \n\n# note\n*.map\n", label="x") == ["dist/", "*.map"]


# ---------- through the API ----------


GITIGNORE_PROJECT = [
    ("repo/.gitignore", "*.log\n!keep.log\ndist/\n.env\n"),
    ("repo/src/app.py", "x"),
    ("repo/src/debug.log", "noise"),
    ("repo/keep.log", "kept"),
    ("repo/dist/bundle.js", "y"),
    ("repo/dist/bundle.js.map", "y"),
    ("repo/.env", "SECRET=1"),
    ("repo/pkg/.gitignore", "/fixtures/\n"),
    ("repo/pkg/fixtures/big.json", "{}"),
    ("repo/pkg/mod.py", "x"),
]


def by_path(body):
    return {item["path"]: item for item in body["exclusions"]}


def test_gitignored_paths_are_shown_but_not_analyzed(upload, client):
    body = upload(build_zip(GITIGNORE_PROJECT)).json()
    exclusions = by_path(body)
    assert exclusions["repo/src/debug.log"] == {
        "nodeId": exclusions["repo/src/debug.log"]["nodeId"],
        "path": "repo/src/debug.log",
        "type": "file",
        "reason": "gitignore",
        "rule": "repo/.gitignore line 1: *.log",
        "entryCount": None,
    }
    assert exclusions["repo/dist"]["type"] == "directory"
    assert exclusions["repo/dist"]["entryCount"] == 2
    assert exclusions["repo/pkg/fixtures"]["rule"] == "repo/pkg/.gitignore line 1: /fixtures/"
    assert "repo/keep.log" not in exclusions

    stats = body["stats"]
    # .gitignore x2, app.py, keep.log, mod.py
    assert stats["totalFiles"] == 5
    assert stats["excludedFileCount"] == 2  # debug.log, .env
    assert stats["excludedDirectoryCount"] == 2
    assert stats["excludedEntryCount"] == 5
    assert body["project"]["exclusionSettings"]["gitignoreFiles"] == ["repo/.gitignore", "repo/pkg/.gitignore"]
    # The ignored .env was never extracted, so there is no secrets warning for it.
    assert not any(w["code"] == "possible_secrets" for w in body["warnings"])

    tree = client.get(f"/api/projects/{body['project']['id']}/tree", params={"depth": 64}).json()
    nodes = {node["path"]: node for node in tree["nodes"]}
    debug = nodes["repo/src/debug.log"]
    assert debug["excluded"] is True and debug["sizeBytes"] is None
    assert nodes["repo/src"]["descendantFileCount"] == 1
    assert nodes["repo/src"]["childCount"] == 2


def test_gitignore_can_be_turned_off(upload):
    body = upload(build_zip(GITIGNORE_PROJECT), respectGitignore=False).json()
    assert body["exclusions"] == []
    assert body["stats"]["totalFiles"] == 10
    assert body["project"]["exclusionSettings"]["gitignoreFiles"] == []


def test_ignored_files_do_not_count_toward_file_limit(make_client, upload):
    client = make_client(max_files=3)
    entries = [("repo/.gitignore", "generated/\n"), ("repo/a.py", "a")]
    entries += [(f"repo/generated/f{i}.py", "x") for i in range(50)]
    response = upload(build_zip(entries), test_client=client)
    assert response.status_code == 201
    assert response.json()["exclusions"][0]["entryCount"] == 50


def test_custom_exclude_and_include_patterns(upload):
    entries = [("p/src/a.py", "a"), ("p/docs/guide.md", "g"), ("p/node_modules/x/i.js", "x"), ("p/b.bak", "b")]
    body = upload(build_zip(entries), excludePatterns="docs/\n*.bak", includePatterns="node_modules/").json()
    exclusions = by_path(body)
    assert exclusions["p/docs"]["rule"] == "custom rule: docs/"
    assert exclusions["p/b.bak"]["reason"] == "custom"
    assert "p/node_modules" not in exclusions
    assert body["stats"]["totalFiles"] == 2
    assert body["project"]["exclusionSettings"]["excludePatterns"] == ["docs/", "*.bak"]
    assert body["project"]["exclusionSettings"]["includePatterns"] == ["node_modules/"]


def test_invalid_patterns_are_rejected_before_any_job(client, temp_root):
    response = client.post(
        "/api/projects/analyze",
        files={"file": ("p.zip", build_zip([("a.txt", "a")]), "application/zip")},
        data={"excludePatterns": "\n".join(f"p{i}" for i in range(150))},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_patterns"
    assert list(temp_root.iterdir()) == []


def test_oversized_gitignore_is_reported_and_not_applied(upload):
    big = "*.log\n" + "#" * MAX_GITIGNORE_BYTES
    body = upload(build_zip([("p/.gitignore", big), ("p/a.log", "x")])).json()
    assert body["stats"]["totalFiles"] == 2
    assert any(w["code"] == "gitignore_not_applied" for w in body["warnings"])


def test_local_scan_applies_policy_and_reads_gitignore(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / ".gitignore").write_text("*.log\n")
    (root / "src" / "a.py").write_text("x")
    (root / "src" / "run.log").write_text("noise!")
    (root / "node_modules" / "pkg" / "i.js").write_text("x")
    result = scan_directory(
        root,
        root_name="proj",
        context=AnalysisContext.started(10),
        max_files=100,
        max_depth=10,
        policy=ExclusionPolicy(),
    )
    nodes = {node.path: node for node in result.nodes.values()}
    assert nodes["src/run.log"].excluded and nodes["src/run.log"].size_bytes == 6
    assert nodes["src/run.log"].excluded_rule == ".gitignore line 1: *.log"
    assert nodes["node_modules"].excluded and "node_modules/pkg" not in nodes
    assert nodes[""].descendant_file_count == 2  # .gitignore + a.py
