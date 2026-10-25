"""Architecture map: parsing, resolution, grouping, roles, connections and their evidence."""

from __future__ import annotations

import pytest

from app.analyzers.parsers import MAX_PARSE_BYTES, parse_imports
from tests.zip_factory import build_zip

MONOREPO = [
    ("shop/package.json", '{"name": "shop", "private": true, "workspaces": ["apps/*", "packages/*"]}'),
    # React web app with a tsconfig path alias (comments and trailing commas, as tsconfig allows)
    ("shop/apps/web/package.json", '{"name": "@shop/web", "dependencies": {"react": "18", "@shop/ui": "*"}}'),
    ("shop/apps/web/tsconfig.json", '{\n  // aliases\n  "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]},},\n}'),
    ("shop/apps/web/src/main.tsx", 'import React from "react";\nimport { App } from "@/App";\nimport "./index.css";\ndocument.getElementById("root");\n'),
    ("shop/apps/web/src/App.tsx", 'import { Button } from "@shop/ui";\nimport { loadOrder } from "./lib/api";\nexport function App() { return <Button />; }\n'),
    ("shop/apps/web/src/lib/api.ts", 'export const loadOrder = (id: string) => fetch(`/api/orders/${id}`);\nexport const pay = () => axios.post("/api/payments/checkout");\n'),
    ("shop/apps/web/src/index.css", "body { margin: 0 }\n"),
    # Shared UI workspace package
    ("shop/packages/ui/package.json", '{"name": "@shop/ui", "main": "index.ts", "dependencies": {"react": "18"}}'),
    ("shop/packages/ui/index.ts", 'export { Button } from "./Button";\n'),
    ("shop/packages/ui/Button.tsx", 'import React from "react";\nexport const Button = () => <button />;\n'),
    # Express API, big enough to be split into components
    ("shop/apps/api/package.json", '{"name": "@shop/api", "main": "src/server.js", "dependencies": {"express": "4", "@prisma/client": "5", "stripe": "14", "bullmq": "5", "jsonwebtoken": "9"}}'),
    ("shop/apps/api/src/server.js", 'const express = require("express");\nconst app = express();\napp.use("/api/orders", require("./routes/orders"));\napp.use("/api/payments", require("./routes/payments"));\napp.use("/api/users", require("./routes/users"));\n'),
    ("shop/apps/api/src/config.js", "module.exports = { port: 3000 };\n"),
    ("shop/apps/api/src/routes/orders.js", 'const router = require("express").Router();\nconst db = require("../db/client");\nconst { requireUser } = require("../auth/jwt");\nrouter.get("/:id", requireUser, async (req, res) => res.json(await db.order.find()));\nmodule.exports = router;\n'),
    ("shop/apps/api/src/routes/payments.js", 'const router = require("express").Router();\nconst Stripe = require("stripe");\nconst queue = require("../jobs/queue");\nrouter.post("/checkout", (req, res) => res.end());\nmodule.exports = router;\n'),
    ("shop/apps/api/src/routes/users.js", 'const router = require("express").Router();\nconst models = require("../db/models");\nrouter.get("/", (req, res) => res.end());\nmodule.exports = router;\n'),
    ("shop/apps/api/src/db/client.js", 'const { PrismaClient } = require("@prisma/client");\nmodule.exports = new PrismaClient();\n'),
    ("shop/apps/api/src/db/models.js", 'const { Prisma } = require("@prisma/client");\nconst client = require("./client");\nmodule.exports = {};\n'),
    ("shop/apps/api/src/auth/jwt.js", 'const jwt = require("jsonwebtoken");\nexports.requireUser = (req, res, next) => jwt.verify();\n'),
    ("shop/apps/api/src/auth/passwords.js", 'const jwt = require("jsonwebtoken");\nmodule.exports = {};\n'),
    ("shop/apps/api/src/jobs/queue.js", 'const { Queue } = require("bullmq");\nmodule.exports = new Queue("emails");\n'),
    ("shop/apps/api/src/jobs/email-worker.js", 'const { Worker } = require("bullmq");\nconst mod = require(someName);\nnew Worker("emails");\n'),
    ("shop/apps/api/src/utils/logger.js", "module.exports = console;\n"),
    ("shop/apps/api/src/utils/missing-import.js", 'const gone = require("./does-not-exist");\n'),
    ("shop/apps/api/src/routes/orders.test.js", 'const request = require("supertest");\nconst orders = require("./orders");\n'),
]

PYTHON_PROJECT = [
    ("svc/pyproject.toml", '[project]\nname = "billing"\ndependencies = ["flask>=3", "SQLAlchemy", "celery", "PyJWT", "requests"]\n'),
    ("svc/src/billing/__init__.py", ""),
    ("svc/src/billing/app.py", "from flask import Flask\nfrom .api import routes\nfrom billing.models import invoice\napp = Flask(__name__)\n"),
    ("svc/src/billing/api/__init__.py", ""),
    ("svc/src/billing/api/routes.py", 'from flask import Blueprint\nfrom ..models.invoice import Invoice\nfrom ..auth import tokens\nbp = Blueprint("billing", __name__, url_prefix="/api/invoices")\n@bp.get("/<int:invoice_id>")\ndef show(invoice_id): ...\n'),
    ("svc/src/billing/models/__init__.py", ""),
    ("svc/src/billing/models/invoice.py", "from sqlalchemy.orm import Mapped\nimport sqlite3\nclass Invoice: ...\n"),
    ("svc/src/billing/models/customer.py", "from sqlalchemy import Column\nfrom . import invoice\n"),
    ("svc/src/billing/auth/__init__.py", ""),
    ("svc/src/billing/auth/tokens.py", "import jwt\nimport os\n"),
    ("svc/src/billing/tasks/__init__.py", ""),
    ("svc/src/billing/tasks/emails.py", "from celery import shared_task\nimport smtplib\nimport requests\n"),
    ("svc/src/billing/tasks/reports.py", "from celery import shared_task\nfrom billing.models.invoice import Invoice\n"),
    ("svc/tests/test_routes.py", "import pytest\nfrom billing.api import routes\n"),
    ("svc/src/billing/broken.py", "def broken(:\n"),
]


def architecture(upload, client, entries, **form):
    body = upload(build_zip(entries), **form).json()
    response = client.get(f"/api/projects/{body['project']['id']}/architecture")
    assert response.status_code == 200
    return body, response.json()


def by_name(arch):
    return {component["name"]: component for component in arch["components"]}


def edge(arch, source_name, target_name):
    names = {c["id"]: c["name"] for c in arch["components"]} | {x["id"]: x["name"] for x in arch["externals"]}
    for connection in arch["connections"]:
        if names[connection["source"]] == source_name and names[connection["target"]] == target_name:
            return connection
    return None


# ---------- parsers ----------


def test_js_parser_ignores_comments_and_strings_and_counts_computed_targets():
    source = b'// import fake from "nope"\nconst s = "import x from \'y\'";\nimport a from "./a";\nrequire(name);\nimport("./lazy");\n'
    result = parse_imports(source, ".js", lambda: False)
    assert [(i.specifier, i.line, i.kind) for i in result.imports] == [("./a", 3, "static"), ("./lazy", 5, "dynamic")]
    assert result.dynamic_unknown == 1


def test_ts_type_imports_and_reexports():
    result = parse_imports(b'import type { T } from "./t";\nexport * from "./all";\nexport const x = 1;\n', ".ts", lambda: False)
    assert [(i.specifier, i.kind) for i in result.imports] == [("./t", "type"), ("./all", "reexport")]


def test_python_parser_relative_levels_and_syntax_errors():
    result = parse_imports(b"from ..models import User, Order\nimport os.path\n", ".py", lambda: False)
    assert [(i.specifier, i.level, i.names) for i in result.imports] == [("models", 2, ("User", "Order")), ("os.path", 0, ())]
    assert parse_imports(b"def (:\n", ".py", lambda: False).error == "syntax_error"


def test_parser_size_cap_and_cancellation():
    assert parse_imports(b"x" * (MAX_PARSE_BYTES + 1), ".js", lambda: False).error == "too_large"
    assert parse_imports(b"const a = 1;\n" * 5000, ".js", lambda: True).error == "parse_cancelled"


def test_route_and_client_detection():
    js = b'router.get("/:id", h);\napp.use("/api/orders", r);\nmap.get("/not-a-route");\nfetch(`/api/orders/${id}`);\nwindow.x;\n'
    result = parse_imports(js, ".js", lambda: False)
    assert result.routes == [("/:id", 1), ("/api/orders", 2)]
    assert ("/api/orders/*", 4) in result.url_refs
    assert result.browser_api is True
    py = b'@router.get("/{item}")\ndef f(): ...\nclient.get("/api/health")\nbp = Blueprint("b", __name__, url_prefix="/api/b")\n'
    assert parse_imports(py, ".py", lambda: False).routes == [("/{item}", 1), ("/api/b", 4)]


# ---------- full map: JS/TS monorepo ----------


@pytest.fixture
def monorepo(upload, client):
    return architecture(upload, client, MONOREPO)


def test_monorepo_components_and_roles(monorepo):
    _, arch = monorepo
    assert arch["status"] == "available"
    components = by_name(arch)
    assert components["@shop/web"]["role"] == "frontend"
    assert components["@shop/web"]["confidence"] == "high"
    assert components["@shop/ui"]["role"] == "frontend"
    assert components["@shop/api · routes"]["role"] == "api"
    assert components["@shop/api · db"]["role"] == "data"
    assert components["@shop/api · db"]["confidence"] == "high"
    assert components["@shop/api · auth"]["role"] == "auth"
    assert components["@shop/api · jobs"]["role"] == "jobs"
    assert components["@shop/api (root files)"]["role"] in ("api", "backend")
    assert set(components) == {
        "@shop/web", "@shop/ui", "@shop/api (root files)", "@shop/api · routes", "@shop/api · db",
        "@shop/api · auth", "@shop/api · jobs", "@shop/api · utils",
    }
    api_routes = components["@shop/api · routes"]
    assert any(e["kind"] == "import" and "routes" in e["detail"] for e in api_routes["evidence"])


def test_monorepo_every_role_has_evidence_with_locations(monorepo):
    _, arch = monorepo
    for component in arch["components"]:
        assert component["evidence"], component["name"]
        for item in component["evidence"]:
            if item["kind"] == "import" and item["path"]:
                assert item["nodeId"] and item["path"].startswith("shop/")


def test_monorepo_connections(monorepo):
    _, arch = monorepo
    # workspace package import (resolved through package.json "main")
    workspace = edge(arch, "@shop/web", "@shop/ui")
    assert workspace and workspace["confidence"] == "high"
    # server internals
    assert edge(arch, "@shop/api · routes", "@shop/api · db")["importCount"] >= 2
    assert edge(arch, "@shop/api · routes", "@shop/api · auth")
    assert edge(arch, "@shop/api · routes", "@shop/api · jobs")
    # frontend → API over HTTP, inferred from URL paths, with evidence on both sides
    http = edge(arch, "@shop/web", "@shop/api (root files)")
    assert http and http["kinds"] == ["http"] and http["confidence"] == "medium"
    assert any("/api/orders" in e["specifier"] and "server.js" in e["target"] for e in http["evidence"])
    # evidence lines point at real imports
    db_edge = edge(arch, "@shop/api · routes", "@shop/api · db")
    assert any(e["path"].endswith("routes/orders.js") and e["line"] == 2 for e in db_edge["evidence"])


def test_monorepo_external_services(monorepo):
    _, arch = monorepo
    externals = {x["name"]: x for x in arch["externals"]}
    assert "Databases" in externals and "Payments" in externals
    assert any("Stripe" in service for service in externals["Payments"]["services"])
    assert edge(arch, "@shop/api · db", "Databases")
    assert edge(arch, "@shop/api · routes", "Payments")


def test_monorepo_frameworks_and_summary(monorepo):
    _, arch = monorepo
    frameworks = {f["name"]: f for f in arch["frameworks"]}
    assert frameworks["React"]["confidence"] == "high"
    assert frameworks["Express"]["importingFiles"] >= 1
    assert frameworks["Prisma"]["declaredIn"] == ["shop/apps/api/package.json"]
    summary = arch["summary"]
    assert summary["dynamicUnknown"] == 1
    assert summary["unresolvedImports"] == 1
    assert arch["unresolvedSamples"][0]["specifier"] == "./does-not-exist"
    assert any("dynamic import" in note for note in arch["notes"])


def test_tsconfig_alias_resolution(upload, client, monorepo):
    body, arch = monorepo
    web = by_name(arch)["@shop/web"]
    details = client.get(f"/api/projects/{body['project']['id']}/architecture/components/{web['id']}").json()
    rows = {row["path"]: row for row in details["files"]}
    main = rows["shop/apps/web/src/main.tsx"]
    assert main["importsInternal"] == 2  # "@/App" via tsconfig paths + "./index.css"
    assert main["externalPackages"] == ["react"]
    assert main["parseStatus"] == "parsed"
    assert details["totalFiles"] == web["fileCount"]


def test_entry_points_from_manifest(monorepo):
    _, arch = monorepo
    root = by_name(arch)["@shop/api (root files)"]
    assert root["entryPoints"] == [
        {"path": "shop/apps/api/src/server.js", "nodeId": root["entryPoints"][0]["nodeId"], "reason": 'package.json "main"'}
    ]


# ---------- full map: Python ----------


def test_python_project(upload, client):
    _, arch = architecture(upload, client, PYTHON_PROJECT)
    components = by_name(arch)
    roles = {name: (c["role"], c["confidence"]) for name, c in components.items()}
    assert set(roles) == {"billing (root files)", "api", "auth", "models", "tasks", "tests"}
    assert roles["api"][0] == "api"  # Blueprint(url_prefix=...) and @bp.get
    assert roles["models"] == ("data", "high")
    assert roles["auth"][0] == "auth"
    assert roles["tasks"][0] == "jobs"
    assert roles["tests"][0] == "tests"
    # relative and absolute (src-layout) imports both resolve
    assert edge(arch, "api", "models")
    assert edge(arch, "tasks", "models")
    assert edge(arch, "tests", "api")
    externals = {x["name"]: x["services"] for x in arch["externals"]}
    assert any("SMTP" in s for s in externals["Email"])  # smtplib is stdlib but still an external service
    assert any("SQLite" in s for s in externals["Databases"])
    assert arch["summary"]["parseErrors"] == 1
    assert {f["name"] for f in arch["frameworks"]} >= {"Flask", "SQLAlchemy", "Celery", "PyJWT"}


# ---------- options, edge cases, API ----------


def test_code_analysis_can_be_turned_off(upload, client):
    body, arch = architecture(upload, client, MONOREPO, analyzeCode=False)
    assert body["project"]["codeAnalysis"] is False
    assert arch["status"] == "disabled"
    assert arch["components"] == []


def test_project_without_code(upload, client):
    _, arch = architecture(upload, client, [("docs/readme.md", "# hi"), ("data/x.csv", "a,b")])
    assert arch["status"] == "no_code"


def test_generated_and_excluded_files_are_not_parsed(upload, client):
    entries = [
        ("p/src/a.js", 'import b from "./b";\n'),
        ("p/src/b.js", "export default 1;\n"),
        ("p/dist/bundle.js", 'import x from "leftpad";\n'),
        ("p/node_modules/z/index.js", 'require("zzz");\n'),
    ]
    _, arch = architecture(upload, client, entries)
    assert arch["summary"]["codeFiles"] == 2
    assert arch["summary"]["externalPackages"] == 0


def test_component_endpoint_validation(client, upload, monorepo):
    body, _ = monorepo
    pid = body["project"]["id"]
    assert client.get(f"/api/projects/{pid}/architecture/components/c000000000000").status_code == 404
    assert client.get(f"/api/projects/{pid}/architecture/components/bad").status_code == 422


def test_parse_budget_produces_partial_map(make_client, upload):
    client = make_client(max_parse_seconds=0.000001)
    body = upload(build_zip(MONOREPO), test_client=client).json()
    arch = client.get(f"/api/projects/{body['project']['id']}/architecture").json()
    assert arch["status"] == "available"
    assert arch["summary"]["parsedFiles"] <= 1
    assert arch["notes"][0].startswith("Partial map")
    assert len(arch["components"]) >= 3  # still grouped and classified by files and folders
