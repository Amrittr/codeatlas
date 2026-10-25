"""JavaScript/TypeScript import extraction with tree-sitter.

Recognised: ``import … from "x"``, ``import "x"``, ``import type … from "x"``,
``export … from "x"``, ``import("x")`` and ``require("x")`` with string-literal targets.
Calls whose target is computed at runtime are counted as ``dynamic_unknown``, not guessed.

It also collects HTTP evidence: route paths passed to ``app.get('/x')``/``router.post(...)``,
URL paths in ``fetch``/``axios`` calls or other ``/api/...`` string literals, and use of
browser globals such as ``document`` and ``window``.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache

import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript

from app.analyzers.parsers import ImportRecord, ParseResult

_CHUNK = 64 * 1024
ROUTE_METHODS = {b"get", b"post", b"put", b"patch", b"delete", b"all", b"use", b"route", b"options", b"head"}
CLIENT_FUNCTIONS = {b"fetch", b"axios", b"ky", b"request", b"got", b"$fetch", b"useFetch", b"useSWR"}
BROWSER_GLOBALS = {b"document", b"window", b"localStorage", b"sessionStorage", b"navigator", b"location", b"history"}


@cache
def _language(extension: str) -> tree_sitter.Language:
    if extension == ".tsx":
        return tree_sitter.Language(tree_sitter_typescript.language_tsx())
    if extension in (".ts", ".mts", ".cts"):
        return tree_sitter.Language(tree_sitter_typescript.language_typescript())
    return tree_sitter.Language(tree_sitter_javascript.language())


def _string_value(node: tree_sitter.Node | None) -> str | None:
    if node is None or node.type != "string":
        return None
    fragments = [child.text.decode("utf-8", "replace") for child in node.children if child.type == "string_fragment"]
    return "".join(fragments) if fragments or node.text in (b'""', b"''") else None


def _url_text(node: tree_sitter.Node | None, *, route: bool = False) -> str | None:
    """A string or template literal as a URL path: substitutions become '*', a leading one is dropped.

    Route declarations may start with a parameter (``/:id``); client paths must start with a literal.
    """
    if node is None:
        return None
    if node.type == "string":
        text = _string_value(node)
    elif node.type == "template_string":
        parts = []
        for child in node.named_children:
            if child.type == "string_fragment":
                parts.append(child.text.decode("utf-8", "replace"))
            elif child.type == "template_substitution":
                parts.append("*" if parts else "")
        text = "".join(parts)
    else:
        return None
    if not text or not text.startswith("/") or len(text) > 300 or " " in text:
        return None
    if not (text[1:2].isalnum() or (route and (text == "/" or text[1:2] in (":", "{", "*")))):
        return None
    return text


def _is_router_object(node: tree_sitter.Node | None) -> bool:
    if node is None or node.type != "identifier":
        return False
    name = node.text.lower()
    return name in (b"app", b"api", b"server", b"fastify", b"route", b"routes", b"r") or name.endswith((b"router", b"app"))


def parse_javascript_imports(data: bytes, extension: str, should_stop: Callable[[], bool]) -> ParseResult:
    # A parser per call: tree-sitter parsers are not thread-safe and are cheap to create.
    parser = tree_sitter.Parser(_language(extension))
    try:
        tree = parser.parse(
            lambda offset, _point: data[offset : offset + _CHUNK],
            progress_callback=lambda _offset, _point: should_stop(),
        )
    except ValueError:  # tree-sitter raises "Parsing failed" when the progress callback cancels
        tree = None
    if tree is None:
        return ParseResult(error="parse_cancelled")

    result = ParseResult(partial=tree.root_node.has_error)
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        node_type = node.type
        if node_type == "import_statement":
            source = _string_value(node.child_by_field_name("source"))
            if source is not None:
                kind = "type" if node.text.startswith(b"import type") else "static"
                result.imports.append(ImportRecord(source, node.start_point[0] + 1, kind))
            continue
        if node_type == "export_statement":
            source = _string_value(node.child_by_field_name("source"))
            if source is not None:
                result.imports.append(ImportRecord(source, node.start_point[0] + 1, "reexport"))
                continue
        elif node_type == "member_expression":
            obj = node.child_by_field_name("object")
            if obj is not None and obj.type == "identifier" and obj.text in BROWSER_GLOBALS:
                result.browser_api = True
        elif node_type in ("string", "template_string"):
            url = _url_text(node)
            if url and (url.startswith("/api/") or "/api/" in url[:12]):
                result.url_refs.append((url, node.start_point[0] + 1))
        if node_type == "call_expression":
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            first_arg = (
                next((child for child in arguments.named_children if child.type != "comment"), None)
                if arguments is not None
                else None
            )
            if function is not None and function.type == "member_expression":
                prop = function.child_by_field_name("property")
                if prop is not None and prop.text in ROUTE_METHODS and _is_router_object(function.child_by_field_name("object")):
                    url = _url_text(first_arg, route=True)
                    if url:
                        result.routes.append((url, node.start_point[0] + 1))
                        stack.extend(reversed(node.children))
                        continue
            callee = function
            if callee is not None and callee.type == "member_expression":
                callee = callee.child_by_field_name("object")
            if callee is not None and callee.text in CLIENT_FUNCTIONS:
                url = _url_text(first_arg)
                if url:
                    result.url_refs.append((url, node.start_point[0] + 1))
            is_import = function is not None and function.type == "import"
            is_require = function is not None and function.type == "identifier" and function.text == b"require"
            if (is_import or is_require) and arguments is not None:
                first = next((child for child in arguments.named_children if child.type != "comment"), None)
                source = _string_value(first)
                if source is not None:
                    kind = "dynamic" if is_import else "require"
                    result.imports.append(ImportRecord(source, node.start_point[0] + 1, kind))
                else:
                    result.dynamic_unknown += 1
        stack.extend(reversed(node.children))
    result.imports.sort(key=lambda record: record.line)
    return result
