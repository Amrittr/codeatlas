from __future__ import annotations

import pytest

from app.repositories.project_store import ProjectStore
from tests.zip_factory import SAMPLE_PROJECT, build_zip


@pytest.fixture
def project(upload):
    return upload(build_zip(SAMPLE_PROJECT), name="sample-app.zip").json()


@pytest.fixture
def pid(project):
    return project["project"]["id"]


def node_by_path(client, pid, path):
    result = client.get(f"/api/projects/{pid}/search", params={"q": path}).json()
    return next(node for node in result["nodes"] if node["path"] == path)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "version": "0.4.0"}


def test_public_config_exposes_limits(client):
    body = client.get("/api/config").json()
    assert body["limits"]["maxFiles"] == 100_000
    assert body["processingMode"] == "server"
    assert {"name": "node_modules", "reason": "dependencies", "label": "Installed third-party dependencies"} in body[
        "defaultExclusions"
    ]


def test_analyze_response_shape(project):
    assert project["project"]["archive"]["fileName"] == "sample-app.zip"
    assert project["project"]["status"] == "completed"
    assert set(project) == {"project", "stats", "exclusions", "exclusionCount", "skipped", "skippedCount", "warnings"}


def test_get_project_returns_same_details(client, project, pid):
    assert client.get(f"/api/projects/{pid}").json() == project


def test_tree_default_depth_is_one_level(client, pid):
    tree = client.get(f"/api/projects/{pid}/tree").json()
    assert tree["rootId"] == "root"
    assert list(tree["children"]) == ["root"]
    assert [node["path"] for node in tree["nodes"]] == ["", "sample-app"]


def test_tree_depth_zero_returns_only_node(client, pid):
    tree = client.get(f"/api/projects/{pid}/tree", params={"depth": 0}).json()
    assert len(tree["nodes"]) == 1
    assert tree["children"] == {}


def test_tree_for_subdirectory(client, pid):
    src = node_by_path(client, pid, "sample-app/src")
    tree = client.get(f"/api/projects/{pid}/tree", params={"nodeId": src["id"], "depth": 1}).json()
    assert [node["name"] for node in tree["nodes"]] == ["src", "components", "styles", "utils", "App.js", "index.js"]
    assert list(tree["children"]) == [src["id"]]


def test_tree_reveal_includes_ancestors_and_siblings(client, pid):
    button = node_by_path(client, pid, "sample-app/src/components/Button.jsx")
    tree = client.get(f"/api/projects/{pid}/tree", params={"nodeId": button["id"], "depth": 0, "reveal": True}).json()
    paths = {node["path"] for node in tree["nodes"]}
    assert {"", "sample-app", "sample-app/src", "sample-app/src/components", "sample-app/README.md"} <= paths
    assert "sample-app/src/components/index.js" in paths
    assert "sample-app/server/main.py" not in paths
    assert len(tree["children"]) == 4


def test_unknown_node(client, pid):
    response = client.get(f"/api/projects/{pid}/tree", params={"nodeId": "nope"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "node_not_found"


def test_unknown_project(client):
    response = client.get(f"/api/projects/{'0' * 32}/tree")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


def test_malformed_project_id(client):
    response = client.get("/api/projects/../../etc/stats")
    assert response.status_code in (404, 422)
    response = client.get("/api/projects/not-a-real-id/stats")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def search(client, pid, **params):
    return client.get(f"/api/projects/{pid}/search", params=params).json()


def test_search_partial_case_insensitive(client, pid):
    result = search(client, pid, q="BUT")
    assert [node["path"] for node in result["nodes"] if node["id"] in result["matchIds"]] == [
        "sample-app/src/components/Button.jsx"
    ]
    assert result["totalMatches"] == 1


def test_search_finds_duplicate_basenames(client, pid):
    result = search(client, pid, q="index.js")
    paths = {node["path"] for node in result["nodes"] if node["id"] in result["matchIds"]}
    assert paths == {"sample-app/src/index.js", "sample-app/src/components/index.js"}


def test_search_includes_ancestors_with_pruned_children(client, pid):
    result = search(client, pid, q="Button")
    by_id = {node["id"]: node for node in result["nodes"]}
    assert {node["path"] for node in result["nodes"]} == {
        "", "sample-app", "sample-app/src", "sample-app/src/components", "sample-app/src/components/Button.jsx"
    }
    components = next(node for node in result["nodes"] if node["name"] == "components")
    assert [by_id[child]["name"] for child in result["children"][components["id"]]] == ["Button.jsx"]


def test_search_by_path(client, pid):
    result = search(client, pid, q="server/api/")
    assert result["totalMatches"] == 2


def test_extension_filter(client, pid):
    assert search(client, pid, extension=".py")["totalMatches"] == 4
    assert search(client, pid, extension="PY")["totalMatches"] == 4
    assert search(client, pid, extension=["(none)"])["totalMatches"] == 4
    assert search(client, pid, extension=[".py", ".ts"])["totalMatches"] == 5


def test_classification_filter(client, pid):
    result = search(client, pid, classification="test")
    paths = {node["path"] for node in result["nodes"] if node["id"] in result["matchIds"]}
    assert paths == {"sample-app/tests/test_routes.py", "sample-app/tests/App.test.js"}


def test_combined_filters(client, pid):
    assert search(client, pid, q="index", extension=".js", classification="source")["totalMatches"] == 2


def test_type_filter(client, pid):
    result = search(client, pid, q="s", type="directory")
    assert all(node["type"] == "directory" for node in result["nodes"] if node["id"] in result["matchIds"])


def test_search_limit_truncates(client, pid):
    result = search(client, pid, q="", type="file", limit=3)
    assert len(result["matchIds"]) == 3
    assert result["totalMatches"] == 22
    assert result["truncated"] is True


def test_invalid_classification_rejected(client, pid):
    response = client.get(f"/api/projects/{pid}/search", params={"classification": "magic"})
    assert response.status_code == 422


def test_delete_project(client, pid):
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 404


def test_missing_file_field(client):
    response = client.post("/api/projects/analyze", data={"applyDefaultExclusions": "true"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_unknown_api_route_is_json(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Unknown API endpoint."}}


def test_security_headers(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_tree_response_size_is_capped(make_client, upload):
    client = make_client(max_tree_response_nodes=5)
    body = upload(build_zip([(f"p/f{i}.txt", "x") for i in range(10)]), test_client=client).json()
    pid = body["project"]["id"]
    assert client.get(f"/api/projects/{pid}/tree", params={"depth": 1}).status_code == 200
    response = client.get(f"/api/projects/{pid}/tree", params={"depth": 5})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "tree_too_large"


def test_frontend_is_served_when_enabled(make_client, tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("<!doctype html><title>CodeAtlas</title>")
    client = make_client(serve_frontend=True, frontend_dir=public)
    response = client.get("/")
    assert response.status_code == 200
    assert "CodeAtlas" in response.text
    assert response.headers["cache-control"] == "no-cache"
    assert client.get("/api/health").status_code == 200


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_store_expires_results(project):
    from app.schemas.project import ProjectDetails

    details = ProjectDetails.model_validate(project)
    clock = FakeClock()
    store = ProjectStore(ttl_seconds=60, max_projects=5, clock=clock)
    store.put(details, index=None)  # type: ignore[arg-type]
    assert store.get(details.project.id) is not None
    clock.now = 61
    assert store.get(details.project.id) is None


def test_store_evicts_oldest_beyond_node_budget(project):
    from app.schemas.project import ProjectDetails

    nodes_each = project["project"]["nodeCount"]
    store = ProjectStore(ttl_seconds=60, max_projects=10, max_nodes=nodes_each * 2, clock=FakeClock())
    ids = []
    for index in range(3):
        details = ProjectDetails.model_validate(project)
        details.project.id = f"{index:032x}"
        store.put(details, index=None)  # type: ignore[arg-type]
        ids.append(details.project.id)
    assert store.get(ids[0]) is None
    assert store.get(ids[1]) is not None and store.get(ids[2]) is not None

    # A single project larger than the whole budget is still kept (it is the newest).
    tiny = ProjectStore(ttl_seconds=60, max_projects=10, max_nodes=1, clock=FakeClock())
    details = ProjectDetails.model_validate(project)
    tiny.put(details, index=None)  # type: ignore[arg-type]
    assert tiny.get(details.project.id) is not None


def test_store_evicts_oldest_beyond_capacity(project):
    from app.schemas.project import ProjectDetails

    store = ProjectStore(ttl_seconds=60, max_projects=2, clock=FakeClock())
    ids = []
    for index in range(3):
        details = ProjectDetails.model_validate(project)
        details.project.id = f"{index:032x}"
        store.put(details, index=None)  # type: ignore[arg-type]
        ids.append(details.project.id)
    assert store.get(ids[0]) is None
    assert store.get(ids[1]) is not None and store.get(ids[2]) is not None
