"""Resolve import specifiers to project files, external packages or built-in modules.

Resolution uses only what is in the archive: relative paths, tsconfig/jsconfig path aliases,
workspace package names, and Python package layouts (including ``src/`` layouts). Anything it
cannot place is reported as unresolved rather than guessed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from app.analyzers.architecture.knowledge import EXTERNAL_SERVICES, NODE_BUILTINS
from app.analyzers.architecture.manifests import Package, TsAliases, _join
from app.analyzers.parsers import ImportRecord

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte", ".d.ts", ".json")
JS_SWAPS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
PY_STDLIB = set(sys.stdlib_module_names)


@dataclass(frozen=True, slots=True)
class Resolution:
    kind: str  # internal | external | builtin | unresolved
    target: str  # file path (internal), package name (external), module (builtin), specifier (unresolved)
    via: str = ""  # how it was resolved: relative | alias | workspace | python-package | python-relative


class Resolver:
    def __init__(self, file_paths: set[str], packages: list[Package], ts_aliases: dict[str, TsAliases]):
        self.files = file_paths
        self.directories = {""}
        for path in file_paths:  # every ancestor folder, not just direct parents (src/ in src/pkg/mod.py)
            parts = path.split("/")[:-1]
            for depth in range(1, len(parts) + 1):
                self.directories.add("/".join(parts[:depth]))
        self.ts_aliases = ts_aliases
        self.workspace = {p.name: p for p in packages if p.kind == "npm" and p.name}
        self.python_roots = self._python_roots(packages)
        self.python_modules = self._python_module_index()

    # ---------- JavaScript / TypeScript ----------

    def resolve_js(self, importer: str, record: ImportRecord) -> Resolution:
        spec = record.specifier.split("?", 1)[0].split("#", 1)[0]
        directory = importer.rsplit("/", 1)[0] if "/" in importer else ""
        if spec.startswith((".", "/")):
            target = self._js_file(_join(directory, spec) if spec.startswith(".") else spec.lstrip("/"))
            return Resolution("internal", target, "relative") if target else Resolution("unresolved", spec)

        alias = self._nearest_alias(directory)
        if alias is not None:
            for pattern, targets in alias.patterns:
                matched = _match_alias(pattern, spec)
                if matched is None:
                    continue
                for candidate in targets:
                    target = self._js_file(_join(alias.base, candidate.replace("*", matched)))
                    if target:
                        return Resolution("internal", target, "alias")

        package = _npm_package_name(spec)
        if spec.startswith("node:") or package in NODE_BUILTINS:
            return Resolution("builtin", package.removeprefix("node:"))
        workspace = self.workspace.get(package)
        if workspace is not None:
            subpath = spec[len(package) :].lstrip("/")
            target = self._workspace_target(workspace, subpath)
            return Resolution("internal", target, "workspace")
        return Resolution("external", package)

    def _nearest_alias(self, directory: str) -> TsAliases | None:
        current = directory
        while True:
            if current in self.ts_aliases:
                return self.ts_aliases[current]
            if not current:
                return None
            current = current.rsplit("/", 1)[0] if "/" in current else ""

    def _js_file(self, path: str) -> str | None:
        if path in self.files:
            return path
        for old, replacements in JS_SWAPS.items():
            if path.endswith(old):
                for new in replacements:
                    if path[: -len(old)] + new in self.files:
                        return path[: -len(old)] + new
        for extension in JS_EXTENSIONS:
            if path + extension in self.files:
                return path + extension
        if path in self.directories or not path:
            for extension in JS_EXTENSIONS:
                candidate = f"{path}/index{extension}" if path else f"index{extension}"
                if candidate in self.files:
                    return candidate
        return None

    def _workspace_target(self, package: Package, subpath: str) -> str:
        base = package.path
        if subpath:
            found = self._js_file(_join(base, subpath)) or self._js_file(_join(base, "src/" + subpath))
            if found:
                return found
        for entry, _reason in package.entry_points:
            found = self._js_file(_join(base, entry))
            if found:
                return found
        for candidate in ("src/index", "index", "lib/index"):
            found = self._js_file(_join(base, candidate))
            if found:
                return found
        return f"{base}/package.json" if base else "package.json"

    # ---------- Python ----------

    def _python_roots(self, packages: list[Package]) -> list[str]:
        roots = {p.path for p in packages if p.kind == "python"}
        roots |= {f"{root}/src" if root else "src" for root in list(roots) if (f"{root}/src" if root else "src") in self.directories}
        # Top-level folders, so wrapper layouts (repo-main/app/...) resolve without a manifest.
        roots |= {path.split("/", 1)[0] for path in self.files if "/" in path}
        roots.add("")
        return sorted(roots, key=lambda root: -root.count("/"))

    def _python_module_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for path in self.files:
            if not path.endswith((".py", ".pyi")):
                continue
            for root in self.python_roots:
                prefix = f"{root}/" if root else ""
                if root and not path.startswith(prefix):
                    continue
                relative = path[len(prefix) :]
                module = relative.rsplit(".", 1)[0].replace("/", ".")
                if module.endswith(".__init__"):
                    module = module[: -len(".__init__")]
                elif module == "__init__":
                    continue
                index.setdefault(module, []).append(path)
        return index

    def resolve_python(self, importer: str, record: ImportRecord) -> list[Resolution]:
        if record.level:
            return self._python_relative(importer, record)
        module = record.specifier
        # "from pkg import mod" may name submodules; prefer those, then fall back to the package itself.
        submodules = [self._python_lookup(importer, f"{module}.{name}") for name in record.names]
        results = [Resolution("internal", target, "python-package") for target in submodules if target]
        if not results:
            target = self._python_lookup(importer, module)
            if target:
                results = [Resolution("internal", target, "python-package")]
        if results:
            return _unique(results)
        top = module.split(".", 1)[0]
        if top in PY_STDLIB and top not in EXTERNAL_SERVICES:
            return [Resolution("builtin", top)]
        return [Resolution("external", top)]

    def _python_lookup(self, importer: str, module: str) -> str | None:
        options = self.python_modules.get(module)
        if not options:
            return None
        if len(options) == 1:
            return options[0]
        # Prefer the copy that shares the longest folder prefix with the importer.
        return max(options, key=lambda path: _shared_prefix(path, importer))

    def _python_relative(self, importer: str, record: ImportRecord) -> list[Resolution]:
        parts = importer.split("/")[:-1]
        for _ in range(record.level - 1):
            if parts:
                parts.pop()
        base = "/".join(parts)
        module_path = _join(base, record.specifier.replace(".", "/")) if record.specifier else base
        results = []
        for name in record.names:
            target = self._py_file(f"{module_path}/{name}" if module_path else name)
            if target:
                results.append(Resolution("internal", target, "python-relative"))
        if not results:
            target = self._py_file(module_path)
            if target:
                results.append(Resolution("internal", target, "python-relative"))
        return _unique(results) or [Resolution("unresolved", "." * record.level + record.specifier)]

    def _py_file(self, path: str) -> str | None:
        for candidate in (f"{path}.py", f"{path}.pyi", f"{path}/__init__.py" if path else "__init__.py"):
            if candidate in self.files:
                return candidate
        return None


def _npm_package_name(spec: str) -> str:
    if spec.startswith("@"):
        return "/".join(spec.split("/", 2)[:2])
    return spec.split("/", 1)[0]


def _match_alias(pattern: str, spec: str) -> str | None:
    if "*" not in pattern:
        return "" if spec == pattern else None
    prefix, suffix = pattern.split("*", 1)
    if spec.startswith(prefix) and spec.endswith(suffix) and len(spec) >= len(prefix) + len(suffix):
        return spec[len(prefix) : len(spec) - len(suffix) if suffix else None]
    return None


def _shared_prefix(a: str, b: str) -> int:
    count = 0
    for x, y in zip(a.split("/"), b.split("/"), strict=False):
        if x != y:
            break
        count += 1
    return count


def _unique(results: list[Resolution]) -> list[Resolution]:
    seen, unique = set(), []
    for item in results:
        if item.target not in seen:
            seen.add(item.target)
            unique.append(item)
    return unique
