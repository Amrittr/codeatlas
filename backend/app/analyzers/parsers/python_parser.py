"""Python import extraction with the standard-library ``ast`` parser.

Also collects declared HTTP routes: FastAPI/Flask/Starlette-style ``@app.get("/x")``
decorators and calls, ``APIRouter(prefix=...)``/``Blueprint(url_prefix=...)`` prefixes,
and Django ``path("x/", ...)`` patterns.
"""

from __future__ import annotations

import ast
import warnings

from app.analyzers.parsers import ImportRecord, ParseResult

ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "route", "api_route", "websocket", "add_url_rule", "head", "options"}
PREFIX_KEYWORDS = {"prefix", "url_prefix"}
DJANGO_PATH_FUNCTIONS = {"path", "re_path"}


def _is_router(expression: ast.expr) -> bool:
    """`app`, `router`, `bp`, `api_router`, `self.app`… but not `client`, `session` or `requests`."""
    name = expression.id if isinstance(expression, ast.Name) else expression.attr if isinstance(expression, ast.Attribute) else ""
    name = name.lower()
    return name in {"app", "api", "router", "bp", "blueprint", "server", "application"} or name.endswith(
        ("router", "_app", "_bp", "blueprint", "_api")
    )


def _route_path(value: object) -> str | None:
    """A declared route path. It may start with a parameter (/{item_id}) or be the bare root '/'."""
    if isinstance(value, str) and value.startswith("/") and len(value) <= 300 and " " not in value:
        if value == "/" or value[1:2].isalnum() or value[1:2] in ("{", "<"):
            return value
    return None


def parse_python_imports(data: bytes) -> ParseResult:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # e.g. SyntaxWarning for invalid escapes in the parsed code
            tree = ast.parse(data, type_comments=False)
    except SyntaxError:
        return ParseResult(error="syntax_error")
    except (ValueError, RecursionError, MemoryError):  # NUL bytes, pathological nesting
        return ParseResult(error="syntax_error")

    result = ParseResult()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(ImportRecord(alias.name, node.lineno, "python"))
        elif isinstance(node, ast.ImportFrom):
            names = tuple(alias.name for alias in node.names if alias.name != "*")
            result.imports.append(ImportRecord(node.module or "", node.lineno, "python", level=node.level, names=names))
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            if name == "import_module":
                result.dynamic_unknown += 1
            first = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            if isinstance(node.func, ast.Attribute) and name in ROUTE_METHODS and _is_router(node.func.value) and _route_path(first):
                result.routes.append((first, node.lineno))
            elif isinstance(node.func, ast.Name) and name in DJANGO_PATH_FUNCTIONS and isinstance(first, str) and first and not first.startswith("^"):
                result.routes.append(("/" + first.lstrip("/"), node.lineno))
            for keyword in node.keywords:
                if keyword.arg in PREFIX_KEYWORDS and isinstance(keyword.value, ast.Constant) and _route_path(keyword.value.value):
                    result.routes.append((keyword.value.value, node.lineno))
    result.imports.sort(key=lambda record: record.line)
    return result
