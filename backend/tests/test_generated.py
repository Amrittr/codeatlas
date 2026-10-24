"""Generated-folder detection: evidence from names, corroborated ambiguous names, no false alarms."""

from __future__ import annotations

from tests.zip_factory import build_zip


def analyze(upload, entries):
    body = upload(build_zip(entries)).json()
    return body, {item["path"]: item for item in body["stats"]["generatedFolders"]}


def tree_nodes(client, body):
    tree = client.get(f"/api/projects/{body['project']['id']}/tree", params={"depth": 64}).json()
    return {node["path"]: node for node in tree["nodes"]}


def test_conventional_dist_with_bundles_is_high_confidence(upload, client):
    body, found = analyze(upload, [
        ("app/src/main.ts", "x"),
        ("app/dist/index.html", "<html>"),
        ("app/dist/assets/index-BK3j8d_a.js", "x"),
        ("app/dist/assets/index-Cx9f2kQ1.css", "x"),
        ("app/dist/assets/index-BK3j8d_a.js.map", "x"),
    ])
    assert found["app/dist"]["confidence"] == "high"
    assert "3 of 4 files" in found["app/dist"]["reason"]
    assert found["app/dist"]["fileCount"] == 4
    assert body["stats"]["generatedFolderCount"] == 1
    nodes = tree_nodes(client, body)
    assert nodes["app/dist"]["generated"] is True
    assert nodes["app/dist/index.html"]["classification"] == "generated"
    assert nodes["app/dist/index.html"]["classificationReason"] == "inside generated folder 'app/dist/'"
    assert nodes["app/dist/assets"]["generated"] is False  # only the shallowest folder is reported
    assert nodes["app/src/main.ts"]["classification"] == "source"


def test_conventional_name_alone_is_medium(upload):
    _, found = analyze(upload, [("p/coverage/index.html", "x"), ("p/coverage/app.js.html", "x")])
    assert found["p/coverage"]["confidence"] == "medium"
    assert found["p/coverage"]["reason"] == "conventional build-output folder name 'coverage/'"


def test_build_folder_of_scripts_is_not_flagged(upload, client):
    """The v0.1 rule marked everything under build/ as generated; real scripts must keep their role."""
    body, found = analyze(upload, [
        ("p/package.json", "{}"),
        ("p/build/webpack.config.js", "x"),
        ("p/build/release.sh", "x"),
        ("p/build/utils.js", "x"),
    ])
    assert found == {}
    assert tree_nodes(client, body)["p/build/release.sh"]["classification"] == "source"


def test_ambiguous_names_need_corroboration(upload):
    _, found = analyze(upload, [
        ("gradle-app/build.gradle", "x"),
        ("gradle-app/build/libs/readme.txt", "x"),
        ("rust/Cargo.toml", "x"),
        ("rust/target/debug/notes.txt", "x"),
        ("dotnet/App.csproj", "x"),
        ("dotnet/bin/Debug/app.dll", "x"),
        ("plain/target/notes.txt", "x"),
        ("tools/out/report.txt", "x"),
    ])
    assert found["gradle-app/build"]["reason"].endswith("next to build.gradle, whose tool writes its output there")
    assert found["rust/target"]["confidence"] == "medium"
    assert found["dotnet/bin"]["confidence"] == "high"  # corroborated and the only file is a .dll
    assert "plain/target" not in found
    assert "tools/out" not in found


def test_unnamed_folder_mostly_artifacts(upload):
    entries = [(f"web/vendor/lib{i}.min.js", "x") for i in range(4)] + [("web/vendor/LICENSE", "x")]
    _, found = analyze(upload, entries)
    assert found["web/vendor"]["confidence"] == "high"
    assert found["web/vendor"]["reason"] == "4 of 5 files are bundles, source maps or compiled output"


def test_small_or_mixed_folders_are_not_flagged(upload):
    _, found = analyze(upload, [
        ("p/static/app.min.js", "x"),
        ("p/static/app.js", "x"),
        ("p/static/style.css", "x"),
        ("p/proto/user_pb2.py", "x"),
        ("p/proto/user.proto", "x"),
    ])
    assert found == {}


def test_excluded_files_do_not_count_as_evidence(upload):
    entries = [("p/.gitignore", "*.map\n"), ("p/dist/a.js", "x")] + [(f"p/dist/a{i}.js.map", "x") for i in range(5)]
    _, found = analyze(upload, entries)
    # Only dist/a.js is analyzed: the name alone gives medium confidence.
    assert found["p/dist"]["confidence"] == "medium"
    assert found["p/dist"]["fileCount"] == 1


def test_generated_counts_flow_into_statistics(upload):
    body, _ = analyze(upload, [("p/src/a.py", "x"), ("p/dist/x.js", "x"), ("p/dist/y.js", "x")])
    classes = {item["classification"]: item["fileCount"] for item in body["stats"]["classifications"]}
    assert classes == {"source": 1, "generated": 2}
