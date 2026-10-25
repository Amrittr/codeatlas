"""Read package manifests and compiler configs as data. Nothing is executed or installed.

Finds package boundaries (package.json, pyproject.toml, setup.py/setup.cfg, requirements*.txt,
manage.py), declared dependencies, JS/TS entry points and tsconfig/jsconfig path aliases.
Files are size-capped and parse errors are tolerated: a broken manifest just contributes less evidence.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.analyzers.architecture.knowledge import PYPI_TO_MODULE

MAX_MANIFEST_BYTES = 256 * 1024
PACKAGE_MARKERS = ("package.json", "pyproject.toml", "setup.py", "setup.cfg", "manage.py")
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass
class Package:
    path: str  # folder relative to the archive root ('' for the root)
    kind: str  # npm | python
    name: str | None = None
    manifest: str = ""  # path of the manifest that defines it
    dependencies: dict[str, str] = field(default_factory=dict)  # import name → declaring manifest
    entry_points: list[tuple[str, str]] = field(default_factory=list)  # (relative path, reason)


@dataclass
class TsAliases:
    base: str  # folder that relative alias targets resolve from
    patterns: list[tuple[str, list[str]]]  # ("@/*", ["src/*"])


def _read(root: Path, path: str) -> bytes | None:
    file = root.joinpath(*path.split("/"))
    try:
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        return file.read_bytes()
    except OSError:
        return None


def _lenient_json(data: bytes):
    """Parse JSON that may contain // and /* */ comments and trailing commas (tsconfig style)."""
    text = data.decode("utf-8", "replace")
    out, i, in_string = [], 0, False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", i):
            i = text.find("\n", i)
            if i == -1:
                break
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        else:
            out.append(char)
        i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    return json.loads(cleaned)


def _module_name(distribution: str) -> str:
    key = distribution.lower().replace("_", "-")
    return PYPI_TO_MODULE.get(key, key.replace("-", "_").replace(".", "_"))


def read_packages(root: Path, files_by_dir: dict[str, list[str]]) -> list[Package]:
    """Find package boundaries among analyzed files. ``files_by_dir`` maps folder → file names."""
    packages: dict[str, Package] = {}
    for directory, names in files_by_dir.items():
        prefix = f"{directory}/" if directory else ""
        lowered = {name.lower(): name for name in names}
        if "package.json" in lowered:
            package = Package(path=directory, kind="npm", manifest=prefix + lowered["package.json"])
            data = _read(root, package.manifest)
            try:
                manifest = json.loads(data) if data else {}
            except (ValueError, UnicodeDecodeError):
                manifest = {}
            if isinstance(manifest, dict):
                package.name = manifest.get("name") if isinstance(manifest.get("name"), str) else None
                for section in ("dependencies", "devDependencies", "peerDependencies"):
                    deps = manifest.get(section)
                    if isinstance(deps, dict):
                        for dep in deps:
                            package.dependencies.setdefault(str(dep), package.manifest)
                for field_name in ("main", "module", "source"):
                    value = manifest.get(field_name)
                    if isinstance(value, str):
                        package.entry_points.append((value.lstrip("./"), f'package.json "{field_name}"'))
                bins = manifest.get("bin")
                if isinstance(bins, str):
                    package.entry_points.append((bins.lstrip("./"), 'package.json "bin"'))
                elif isinstance(bins, dict):
                    package.entry_points.extend((str(v).lstrip("./"), 'package.json "bin"') for v in bins.values() if isinstance(v, str))
            packages[directory] = package

        python_markers = [lowered[m] for m in ("pyproject.toml", "setup.py", "setup.cfg", "manage.py") if m in lowered]
        requirements = [name for name in names if name.lower().startswith("requirements") and name.lower().endswith(".txt")]
        if python_markers or requirements:
            existing = packages.get(directory)
            package = existing or Package(path=directory, kind="python", manifest=prefix + (python_markers or requirements)[0])
            if "pyproject.toml" in lowered:
                data = _read(root, prefix + lowered["pyproject.toml"])
                try:
                    pyproject = tomllib.loads(data.decode("utf-8", "replace")) if data else {}
                except (tomllib.TOMLDecodeError, ValueError):
                    pyproject = {}
                project = pyproject.get("project", {}) if isinstance(pyproject, dict) else {}
                if isinstance(project, dict):
                    if isinstance(project.get("name"), str) and not package.name:
                        package.name = project["name"]
                    for requirement in project.get("dependencies", []) or []:
                        match = _REQUIREMENT_NAME.match(str(requirement))
                        if match:
                            package.dependencies.setdefault(_module_name(match.group(1)), prefix + "pyproject.toml")
                poetry = pyproject.get("tool", {}).get("poetry", {}) if isinstance(pyproject.get("tool"), dict) else {}
                if isinstance(poetry, dict) and isinstance(poetry.get("dependencies"), dict):
                    for dep in poetry["dependencies"]:
                        if dep.lower() != "python":
                            package.dependencies.setdefault(_module_name(dep), prefix + "pyproject.toml")
            for requirement_file in requirements:
                data = _read(root, prefix + requirement_file)
                for line in (data or b"").decode("utf-8", "replace").splitlines():
                    if line.strip().startswith(("#", "-")):
                        continue
                    match = _REQUIREMENT_NAME.match(line)
                    if match:
                        package.dependencies.setdefault(_module_name(match.group(1)), prefix + requirement_file)
            for entry in ("manage.py", "main.py", "app.py", "wsgi.py", "asgi.py", "__main__.py"):
                if entry in lowered:
                    package.entry_points.append((lowered[entry], "conventional Python entry point"))
            packages[directory] = package
    return sorted(packages.values(), key=lambda item: (item.path.count("/"), item.path))


def read_ts_aliases(root: Path, files_by_dir: dict[str, list[str]]) -> dict[str, TsAliases]:
    """tsconfig.json / jsconfig.json ``compilerOptions.paths`` per folder."""
    aliases: dict[str, TsAliases] = {}
    for directory, names in files_by_dir.items():
        for config_name in ("tsconfig.json", "jsconfig.json"):
            if config_name not in names:
                continue
            prefix = f"{directory}/" if directory else ""
            data = _read(root, prefix + config_name)
            try:
                config = _lenient_json(data) if data else {}
            except ValueError:
                continue
            options = config.get("compilerOptions", {}) if isinstance(config, dict) else {}
            paths = options.get("paths") if isinstance(options, dict) else None
            if not isinstance(paths, dict):
                continue
            base_url = options.get("baseUrl", ".") if isinstance(options.get("baseUrl", "."), str) else "."
            base = _join(directory, base_url)
            patterns = [(str(key), [str(t) for t in targets if isinstance(t, str)]) for key, targets in paths.items() if isinstance(targets, list)]
            aliases[directory] = TsAliases(base=base, patterns=patterns)
            break
    return aliases


def _join(directory: str, relative: str) -> str:
    parts = [p for p in directory.split("/") if p]
    for piece in relative.replace("\\", "/").split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if parts:
                parts.pop()
        else:
            parts.append(piece)
    return "/".join(parts)
