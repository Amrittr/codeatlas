"""Language adapters that extract import statements from source files.

Each adapter takes the file's bytes and returns ``ParseResult``: the imports it found, with
line numbers, and whether parsing was complete. Adapters use real parsers (Python's ``ast``,
tree-sitter for JavaScript/TypeScript), so comments and strings that merely look like imports
are never reported. Code is parsed, never executed.

Adding a language means adding an adapter module and registering its extensions in ``ADAPTERS``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

MAX_PARSE_BYTES = 512 * 1024


@dataclass(frozen=True, slots=True)
class ImportRecord:
    specifier: str
    line: int
    kind: str  # static | reexport | type | dynamic | require | python
    level: int = 0  # Python relative-import level (from .. import x → 2)
    names: tuple[str, ...] = ()  # Python "from x import a, b" names, used to resolve submodules


@dataclass(slots=True)
class ParseResult:
    imports: list[ImportRecord] = field(default_factory=list)
    # HTTP evidence for linking clients to servers (see architecture.http_links).
    routes: list[tuple[str, int]] = field(default_factory=list)  # paths this file declares as server routes
    url_refs: list[tuple[str, int]] = field(default_factory=list)  # URL paths this file calls or references
    browser_api: bool = False  # uses document/window/localStorage …, i.e. runs in a browser
    dynamic_unknown: int = 0  # import()/require() calls whose target is not a string literal
    error: str | None = None  # syntax_error | too_large | unreadable | parse_cancelled | parse_timeout | parser_crashed
    partial: bool = False  # parsed with recoverable syntax errors


Adapter = Callable[[bytes, str, Callable[[], bool]], ParseResult]


def _python(data: bytes, extension: str, should_stop: Callable[[], bool]) -> ParseResult:
    from app.analyzers.parsers.python_parser import parse_python_imports

    return parse_python_imports(data)


def _javascript(data: bytes, extension: str, should_stop: Callable[[], bool]) -> ParseResult:
    from app.analyzers.parsers.javascript_parser import parse_javascript_imports

    return parse_javascript_imports(data, extension, should_stop)


ADAPTERS: dict[str, tuple[str, Adapter]] = {
    ".py": ("Python", _python),
    ".pyi": ("Python", _python),
    ".js": ("JavaScript", _javascript),
    ".mjs": ("JavaScript", _javascript),
    ".cjs": ("JavaScript", _javascript),
    ".jsx": ("JavaScript", _javascript),
    ".ts": ("TypeScript", _javascript),
    ".mts": ("TypeScript", _javascript),
    ".cts": ("TypeScript", _javascript),
    ".tsx": ("TypeScript", _javascript),
}


def parse_imports(data: bytes, extension: str, should_stop: Callable[[], bool]) -> ParseResult:
    if len(data) > MAX_PARSE_BYTES:
        return ParseResult(error="too_large")
    _, adapter = ADAPTERS[extension]
    return adapter(data, extension, should_stop)
