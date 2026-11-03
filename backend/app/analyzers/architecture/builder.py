"""Build the architecture map from extracted files. See the package docstring for the pipeline."""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.analyzers.architecture.knowledge import (
    EXTERNAL_CATEGORIES,
    FOLDER_ROLES,
    FRONTEND_EXTENSIONS,
    PY_FILE_ROLES,
    ROLES,
    external_service,
    role_signal,
)
from app.analyzers.architecture.http_links import RouteRef, link_http
from app.analyzers.architecture.manifests import Package, read_packages, read_ts_aliases
from app.analyzers.architecture.resolver import Resolution, Resolver
from app.analyzers.parsers import ADAPTERS, MAX_PARSE_BYTES, ImportRecord, ParseResult
from app.analyzers.parsers.worker import IsolatedParser
from app.schemas.architecture import (
    ArchitectureResponse,
    ArchitectureSummary,
    Component,
    ComponentDetails,
    ComponentFile,
    Connection,
    EdgeEvidence,
    EntryPoint,
    Evidence,
    External,
    Framework,
    LanguageCount,
)
from app.schemas.project import Classification, Confidence
from app.services.analysis_context import AnalysisContext
from app.services.nodes import DirectoryRecord, FileRecord
from app.services.scan_service import node_id

MIN_FILES_TO_SPLIT = 12
MIN_FILES_TO_SPLIT_CHILD = 15
MAX_SPLIT_DEPTH = 3
MAX_COMPONENTS = 36
MAX_EVIDENCE = 5
MAX_UNRESOLVED_SAMPLES = 20
MAX_COMPONENT_FILES_LISTED = 500


@dataclass(slots=True)
class _FileFacts:
    path: str
    language: str | None
    status: str = "not_parsed"
    internal: list[tuple[str, ImportRecord, str]] = field(default_factory=list)  # (target, record, via)
    externals: list[tuple[str, ImportRecord, str]] = field(default_factory=list)  # (package, record, full module)
    imported_by: int = 0
    routes: list[tuple[str, int]] = field(default_factory=list)
    url_refs: list[tuple[str, int]] = field(default_factory=list)
    browser_api: bool = False


def empty_architecture(status: str) -> ArchitectureResult:
    summary = ArchitectureSummary(
        code_files=0, parsed_files=0, parse_errors=0, partially_parsed=0, skipped_too_large=0, imports=0,
        internal_imports=0, external_packages=0, unresolved_imports=0, dynamic_unknown=0, languages=[],
    )
    note = "Code analysis was turned off for this upload, so no source files were read." if status == "disabled" else ""
    response = ArchitectureResponse(
        project_id="", status=status, summary=summary, frameworks=[], components=[], externals=[], connections=[],
        unresolved_samples=[], notes=[note] if note else [],
    )
    return ArchitectureResult(response=response, component_files={})


@dataclass
class ArchitectureResult:
    response: ArchitectureResponse  # project_id filled in when served
    # component id → compact file rows: (path, language, internal_out, imported_by, externals, status)
    component_files: dict[str, list[tuple[str, str | None, int, int, tuple[str, ...], str]]]

    def details(self, component_id: str) -> ComponentDetails | None:
        component = next((item for item in self.response.components if item.id == component_id), None)
        if component is None:
            return None
        rows = self.component_files.get(component_id, [])
        files = [
            ComponentFile(
                node_id=node_id(path), path=path, language=language, imports_internal=out, imported_by=incoming,
                external_packages=list(externals), parse_status=status,
            )
            for path, language, out, incoming, externals, status in rows[:MAX_COMPONENT_FILES_LISTED]
        ]
        return ComponentDetails(component=component, files=files, total_files=len(rows))


def _stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.blake2b(value.encode(), digest_size=6).hexdigest()


def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _is_under(path: str, folder: str) -> bool:
    return not folder or path == folder or path.startswith(folder + "/")


def build_architecture(
    extract_dir: Path,
    nodes: dict[str, FileRecord | DirectoryRecord],
    root_id: str,
    context: AnalysisContext,
    *,
    parse_budget_seconds: float = 150.0,
    parse_file_seconds: float = 5.0,
) -> ArchitectureResult:
    generated = [n.path for n in nodes.values() if isinstance(n, DirectoryRecord) and n.generated]
    analyzed = [n for n in nodes.values() if isinstance(n, FileRecord) and not n.excluded]
    all_paths = {n.path for n in analyzed}
    files_by_dir: dict[str, list[str]] = defaultdict(list)
    for file in analyzed:
        files_by_dir[_parent(file.path)].append(file.name)

    code = [
        f for f in analyzed
        if f.classification in (Classification.SOURCE, Classification.TEST)
        and not any(_is_under(f.path, folder) for folder in generated)
    ]
    facts = {f.path: _FileFacts(f.path, f.language) for f in code}
    by_path = {f.path: f for f in code}

    # 1. Manifests (data only).
    packages = read_packages(extract_dir, files_by_dir)
    aliases = read_ts_aliases(extract_dir, files_by_dir)

    # 2. Parse imports.
    parseable = [f for f in code if f.extension in ADAPTERS]
    context.set_phase("parsing", total=len(parseable))
    results: dict[str, ParseResult] = {}
    parse_deadline = time.monotonic() + parse_budget_seconds
    budget_skipped = 0
    with IsolatedParser(per_file_seconds=parse_file_seconds, should_stop=context.should_stop) as parser:
        for file in parseable:
            context.checkpoint()
            if time.monotonic() > parse_deadline:
                budget_skipped += 1  # leave it "not_parsed"; the map is built from what was parsed
                context.advance()
                continue
            if (file.size_bytes or 0) > MAX_PARSE_BYTES:
                result = ParseResult(error="too_large")
            else:
                result = parser.parse(extract_dir.joinpath(*file.path.split("/")), file.extension)
            results[file.path] = result
            fact = facts[file.path]
            fact.routes = sorted(set(result.routes))
            route_lines = {line for _, line in fact.routes}
            fact.url_refs = sorted({ref for ref in result.url_refs if ref[1] not in route_lines})
            fact.browser_api = result.browser_api
            fact.status = (
                "too_large" if result.error == "too_large" else "error" if result.error else "partial" if result.partial else "parsed"
            )
            context.advance()
    context.checkpoint()

    # 3. Resolve.
    context.set_phase("mapping")
    resolver = Resolver(all_paths, packages, aliases)
    unresolved_samples: list[EdgeEvidence] = []
    unresolved = dynamic_unknown = total_imports = 0
    for path, result in results.items():
        dynamic_unknown += result.dynamic_unknown
        is_python = by_path[path].extension in (".py", ".pyi")
        for record in result.imports:
            total_imports += 1
            resolutions: list[Resolution] = (
                resolver.resolve_python(path, record) if is_python else [resolver.resolve_js(path, record)]
            )
            for resolution in resolutions:
                if resolution.kind == "internal":
                    facts[path].internal.append((resolution.target, record, resolution.via))
                    if resolution.target in facts:
                        facts[resolution.target].imported_by += 1
                elif resolution.kind == "external":
                    full = record.specifier if is_python else resolution.target
                    facts[path].externals.append((resolution.target, record, full))
                elif resolution.kind == "unresolved":
                    unresolved += 1
                    if len(unresolved_samples) < MAX_UNRESOLVED_SAMPLES:
                        unresolved_samples.append(
                            EdgeEvidence(path=path, node_id=node_id(path), line=record.line, specifier=record.specifier, target="?")
                        )
    context.checkpoint()

    # 4. Components.
    groups = _group(code, packages, nodes, root_id)
    component_of: dict[str, str] = {}
    for group in groups:
        for file in group.files:
            component_of[file.path] = group.id

    def component_for_path(path: str) -> str | None:
        if path in component_of:
            return component_of[path]
        best = None
        for group in groups:  # non-code targets (json, css, package.json) map to their folder's component
            if _is_under(path, group.path) and (best is None or len(group.path) > len(best.path)):
                best = group
        return best.id if best else None

    routes = [RouteRef(component_of[p], p, line, url) for p, f in facts.items() if p in component_of for url, line in f.routes]
    clients = [RouteRef(component_of[p], p, line, url) for p, f in facts.items() if p in component_of for url, line in f.url_refs]
    http_links = link_http(routes, clients)
    connections, externals = _connections(groups, facts, component_of, component_for_path, http_links)
    components = [_describe(group, facts, packages, connections) for group in groups]
    _apply_structural_roles(components, connections)

    frameworks = _frameworks(facts, packages)
    languages = Counter(f.language for f in code if f.language)
    parsed = [r for r in results.values() if r.error is None]
    summary = ArchitectureSummary(
        code_files=len(code),
        parsed_files=len(parsed),
        parse_errors=sum(1 for r in results.values() if r.error not in (None, "too_large")),
        partially_parsed=sum(1 for r in parsed if r.partial),
        skipped_too_large=sum(1 for r in results.values() if r.error == "too_large"),
        imports=total_imports,
        internal_imports=sum(len(f.internal) for f in facts.values()),
        external_packages=len({pkg for f in facts.values() for pkg, _, _ in f.externals}),
        unresolved_imports=unresolved,
        dynamic_unknown=dynamic_unknown,
        languages=[LanguageCount(language=lang, file_count=count) for lang, count in languages.most_common()],
    )
    stuck_files = sum(1 for r in results.values() if r.error in ("parse_timeout", "parser_crashed"))
    response = ArchitectureResponse(
        project_id="",
        status="available" if code else "no_code",
        summary=summary,
        frameworks=frameworks,
        components=components,
        externals=externals,
        connections=connections,
        unresolved_samples=unresolved_samples,
        notes=_notes(summary, languages, components, budget_skipped, stuck_files),
    )
    component_files = {
        group.id: sorted(
            (
                (
                    f.path, f.language, len(facts[f.path].internal), facts[f.path].imported_by,
                    tuple(sorted({pkg for pkg, _, _ in facts[f.path].externals})), facts[f.path].status,
                )
                for f in group.files
            ),
            key=lambda row: (-row[3], -row[2], row[0]),
        )
        for group in groups
    }
    return ArchitectureResult(response=response, component_files=component_files)


# ---------------------------------------------------------------- grouping


@dataclass
class _Group:
    id: str
    path: str
    name: str
    package: Package | None
    files: list[FileRecord]
    whole_package: bool = False  # the package was small enough to stay one component


def _group(code: list[FileRecord], packages: list[Package], nodes, root_id) -> list[_Group]:
    """Package boundaries first, then top-level source folders inside each package."""
    roots = sorted({p.path for p in packages}, key=lambda path: -path.count("/") if path else 1)
    package_by_path = {p.path: p for p in packages}
    owners: dict[str, list[FileRecord]] = defaultdict(list)
    base = _project_base(nodes, root_id)
    for file in code:
        owner = next((root for root in roots if root and _is_under(file.path, root)), None)
        if owner is None:
            owner = "" if "" in package_by_path else base
        owners[owner].append(file)

    multiple_packages = len(owners) > 1
    groups: list[_Group] = []
    for root, files in sorted(owners.items()):
        package = package_by_path.get(root)
        label = (package.name if package and package.name else root.rsplit("/", 1)[-1]) or "project"
        splits = [
            (folder if is_root_files else _common_folder(members, folder), members, is_root_files)
            for folder, members, is_root_files in _split(root, files, depth=0, total=len(files))
        ]
        if len(splits) == 1:
            folder, members, _ = splits[0]
            groups.append(_Group(_stable_id("c", f"{root}|package"), folder, label, package, members, whole_package=True))
            continue
        # Name components relative to the package's common source folder (src/, src/billing/ …).
        base = _naming_base([folder for folder, _, _ in splits], root)
        for folder, members, is_root_files in splits:
            anchor = base if _is_under(folder, base) else root
            relative = folder[len(anchor) :].lstrip("/") if anchor else folder
            if not relative:
                owner_name = label if (multiple_packages or anchor == root) else anchor.rsplit("/", 1)[-1]
                name = f"{owner_name} (root files)" if is_root_files else owner_name
            else:
                name = f"{label} · {relative}" if multiple_packages else relative
                if is_root_files:
                    name += " (root files)"
            groups.append(_Group(_stable_id("c", f"{folder}|{is_root_files}"), folder, name, package, members))

    if len(groups) > MAX_COMPONENTS:
        groups = _merge_small(groups)
    return sorted(groups, key=lambda group: group.path)


def _project_base(nodes, root_id) -> str:
    """The single top-level folder of a wrapped archive (repo-main/), else the archive root."""
    top = [n for n in nodes.values() if n.parent_id == root_id]
    if len(top) == 1 and isinstance(top[0], DirectoryRecord):
        return top[0].path
    return ""


def _split(folder: str, files: list[FileRecord], depth: int, total: int) -> list[tuple[str, list[FileRecord], bool]]:
    if depth == 0 and len(files) < MIN_FILES_TO_SPLIT:
        return [(folder, files, False)]
    prefix_len = len(folder) + 1 if folder else 0
    children: dict[str, list[FileRecord]] = defaultdict(list)
    direct: list[FileRecord] = []
    for file in files:
        rest = file.path[prefix_len:]
        if "/" in rest:
            children[rest.split("/", 1)[0]].append(file)
        else:
            direct.append(file)

    # Pass through a single wrapper folder (or a dominant src/) without making it a component.
    dominant = [name for name, members in children.items() if name == "src" and len(members) >= 0.5 * len(files)]
    if depth < MAX_SPLIT_DEPTH and ((len(children) == 1 and not direct) or dominant):
        name = dominant[0] if dominant else next(iter(children))
        inner = _split(_child(folder, name), children[name], depth + 1, total)
        taken = {f.path for f in children[name]}
        rest = [f for f in files if f.path not in taken]
        return inner + (_split_rest(folder, rest) if rest else [])

    result: list[tuple[str, list[FileRecord], bool]] = []
    if direct:
        result.append((folder, direct, True))
    for name, members in sorted(children.items()):
        child = _child(folder, name)
        sub_children = {m.path[len(child) + 1 :].split("/", 1)[0] for m in members if "/" in m.path[len(child) + 1 :]}
        if depth < MAX_SPLIT_DEPTH - 1 and len(members) >= MIN_FILES_TO_SPLIT_CHILD and len(sub_children) >= 2:
            result.extend(_split(child, members, depth + 1, total))
        else:
            result.append((child, members, False))
    return result


def _split_rest(folder: str, files: list[FileRecord]) -> list[tuple[str, list[FileRecord], bool]]:
    groups: dict[str, list[FileRecord]] = defaultdict(list)
    prefix_len = len(folder) + 1 if folder else 0
    for file in files:
        rest = file.path[prefix_len:]
        groups[_child(folder, rest.split("/", 1)[0]) if "/" in rest else folder].append(file)
    return [(path, members, path == folder) for path, members in sorted(groups.items())]


def _naming_base(folders: list[str], root: str) -> str:
    """Deepest folder under ``root`` that holds at least 60% of the components (src/, src/billing/ …).

    Names are shown relative to it, so layout folders do not repeat in every name.
    """
    best = root
    counts: Counter[str] = Counter()
    for folder in folders:
        parts = folder.split("/") if folder else []
        for depth in range(len(parts) + 1):
            prefix = "/".join(parts[:depth])
            if _is_under(prefix, root):
                counts[prefix] += 1
    for prefix, count in counts.items():
        if count >= max(2, 0.6 * len(folders)) and prefix.count("/") > best.count("/") and _is_under(prefix, root):
            best = prefix
    return best


def _common_folder(files: list[FileRecord], default: str) -> str:
    """The deepest folder containing every file, so a lone scripts/ group is named 'scripts'."""
    parents = [file.path.split("/")[:-1] for file in files]
    if not parents:
        return default
    common = []
    for parts in zip(*parents, strict=False):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    folder = "/".join(common)
    return folder if _is_under(folder, default) else default


def _child(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


def _merge_small(groups: list[_Group]) -> list[_Group]:
    groups = sorted(groups, key=lambda group: -len(group.files))
    keep, rest = groups[: MAX_COMPONENTS - 1], groups[MAX_COMPONENTS - 1 :]
    merged_files = [file for group in rest for file in group.files]
    keep.append(_Group(_stable_id("c", "|other"), "", f"Other ({len(rest)} small folders)", None, merged_files))
    return keep


# ---------------------------------------------------------------- roles


def _describe(group: _Group, facts: dict[str, _FileFacts], packages: list[Package], connections: list[Connection]) -> Component:
    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[Evidence]] = defaultdict(list)
    strong: dict[str, int] = defaultdict(int)
    frameworks: Counter[str] = Counter()

    importing_files: dict[str, set[str]] = defaultdict(set)
    for file in group.files:
        for package, record, full in facts[file.path].externals:
            signal = role_signal(package, full)
            if signal is None:
                continue
            role, framework = signal
            if role == "api":
                role = "backend"  # importing a web framework makes it server code; declaring routes makes it the API
            frameworks[framework] += 1
            if file.path not in importing_files[role]:
                importing_files[role].add(file.path)
                if len(evidence[role]) < 3:
                    evidence[role].append(
                        Evidence(kind="import", detail=f"imports {record.specifier} ({framework})", path=file.path, node_id=node_id(file.path), line=record.line)
                    )
    route_files = [f for f in group.files if facts[f.path].routes]
    if route_files:
        importing_files["api"].update(f.path for f in route_files)
        sample = route_files[0]
        url, line = facts[sample.path].routes[0]
        evidence["api"].insert(0, Evidence(
            kind="import", detail=f"declares HTTP routes in {len(route_files)} file(s), e.g. {url}",
            path=sample.path, node_id=node_id(sample.path), line=line,
        ))
    browser_files = [f for f in group.files if facts[f.path].browser_api]
    if browser_files:
        importing_files["frontend"].update(f.path for f in browser_files)
        evidence["frontend"].insert(0, Evidence(
            kind="import", detail=f"{len(browser_files)} file(s) use browser APIs (document, window, localStorage …)",
            path=browser_files[0].path, node_id=node_id(browser_files[0].path),
        ))
    for role, files in importing_files.items():
        scores[role] += 3 * len(files)
        strong[role] = len(files)

    if group.package is not None and (group.whole_package or group.path == group.package.path):
        for dependency, manifest in group.package.dependencies.items():
            signal = role_signal(dependency)
            if signal and signal[0] != "tests":
                role, framework = signal
                role = "backend" if role == "api" else role
                scores[role] += 2
                if not any(e.kind == "manifest" for e in evidence[role]):
                    evidence[role].append(Evidence(kind="manifest", detail=f"{manifest.rsplit('/', 1)[-1]} declares {dependency} ({framework})", path=manifest, node_id=node_id(manifest)))

    count = len(group.files)
    ui_files = sum(1 for f in group.files if f.extension in FRONTEND_EXTENSIONS)
    if count and ui_files / count >= 0.3:
        scores["frontend"] += 4 * ui_files / count
        evidence["frontend"].append(Evidence(kind="file-types", detail=f"{ui_files} of {count} files are UI files (.jsx/.tsx/.vue/.svelte/.css …)"))
    tests = sum(1 for f in group.files if f.classification == Classification.TEST)
    if count and tests / count >= 0.6:
        scores["tests"] += 10
        evidence["tests"].append(Evidence(kind="file-types", detail=f"{tests} of {count} files are tests (by naming convention)"))
        strong["tests"] = tests

    folder_name = group.path.rsplit("/", 1)[-1].lower() if group.path else ""
    if folder_name in FOLDER_ROLES:
        role = FOLDER_ROLES[folder_name]
        scores[role] += 1.5
        evidence[role].append(Evidence(kind="convention", detail=f"folder named '{folder_name}/'", path=group.path, node_id=node_id(group.path)))
    py_roles = Counter(PY_FILE_ROLES[f.name] for f in group.files if f.name in PY_FILE_ROLES)
    for role, hits in py_roles.items():
        scores[role] += min(hits, 3)
        sample = next(f for f in group.files if PY_FILE_ROLES.get(f.name) == role)
        evidence[role].append(Evidence(kind="convention", detail=f"contains {sample.name} (Python naming convention)", path=sample.path, node_id=node_id(sample.path)))

    if scores:
        role = max(scores, key=lambda key: (scores[key], strong.get(key, 0)))
        kinds = {e.kind for e in evidence[role]}
        if strong.get(role, 0) >= 2 or (strong.get(role, 0) >= 1 and "manifest" in kinds):
            confidence = Confidence.HIGH
        elif kinds & {"import", "manifest", "file-types"}:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW
        role_evidence = evidence[role]
    else:
        role, confidence = "module", Confidence.LOW
        role_evidence = [Evidence(kind="structure", detail="no role evidence found; grouped by folder")]

    languages = Counter(f.language for f in group.files if f.language)
    entry_points = []
    if group.package is not None:
        for entry, reason in group.package.entry_points:
            full = f"{group.package.path}/{entry}" if group.package.path else entry
            match = next((f for f in group.files if f.path == full or f.path.rsplit(".", 1)[0] == full.rsplit(".", 1)[0]), None)
            if match:
                entry_points.append(EntryPoint(path=match.path, node_id=node_id(match.path), reason=reason))
    return Component(
        id=group.id,
        name=group.name,
        path=group.path,
        node_id=node_id(group.path) if group.path else None,
        package_name=group.package.name if group.package else None,
        role=role,
        role_label=ROLES[role],
        confidence=confidence,
        evidence=role_evidence[:MAX_EVIDENCE],
        file_count=count,
        parsed_file_count=sum(1 for f in group.files if facts[f.path].status in ("parsed", "partial")),
        languages=[LanguageCount(language=lang, file_count=n) for lang, n in languages.most_common(4)],
        frameworks=[name for name, _ in frameworks.most_common(4)],
        entry_points=entry_points[:3],
    )


def _apply_structural_roles(components: list[Component], connections: list[Connection]) -> None:
    """A weakly-classified leaf that several non-test components import is a shared library.

    Tests import everything, so they do not count as users. A component that itself depends on
    several others is business logic rather than a library, so it keeps its own (weaker) role.
    """
    tests = {component.id for component in components if component.role == "tests"}
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for connection in connections:
        if connection.target_type == "component" and "http" not in connection.kinds:
            if connection.source not in tests:
                incoming[connection.target].add(connection.source)
            outgoing[connection.source].add(connection.target)
    for component in components:
        users = len(incoming[component.id])
        is_leaf = len(outgoing[component.id]) <= 1
        if users >= 2 and is_leaf and component.confidence != Confidence.HIGH and component.role in ("module", "shared", "service", "config"):
            component.role = "shared"
            component.role_label = ROLES["shared"]
            component.confidence = Confidence.MEDIUM
            component.evidence = [Evidence(kind="structure", detail=f"imported by {users} other components")] + component.evidence[: MAX_EVIDENCE - 1]


# ---------------------------------------------------------------- connections


def _connections(groups, facts, component_of, component_for_path, http_links) -> tuple[list[Connection], list[External]]:
    internal: dict[tuple[str, str], dict] = {}
    external: dict[tuple[str, str], dict] = {}
    services: dict[str, Counter[str]] = defaultdict(Counter)
    for path, fact in facts.items():
        source = component_of.get(path)
        if source is None:
            continue
        for target_path, record, _via in fact.internal:
            target = component_for_path(target_path)
            if target is None or target == source:
                continue
            bucket = internal.setdefault((source, target), {"imports": 0, "files": set(), "kinds": set(), "evidence": []})
            _add(bucket, path, record, target_path)
        for package, record, _full in fact.externals:
            service = external_service(package)
            if service is None:
                continue
            category, label = service
            services[category][f"{label} ({package})"] += 1
            bucket = external.setdefault((source, f"x-{category}"), {"imports": 0, "files": set(), "kinds": set(), "evidence": []})
            _add(bucket, path, record, package)

    for link in sorted(http_links, key=lambda item: item.confidence != Confidence.MEDIUM):
        bucket = internal.setdefault(
            (link.client.component, link.server.component),
            {"imports": 0, "files": set(), "kinds": set(), "evidence": [], "http_confidence": link.confidence},
        )
        bucket["kinds"].add("http")
        bucket["files"].add(link.client.path)
        bucket.setdefault("http_confidence", link.confidence)
        if link.confidence == Confidence.MEDIUM:
            bucket["http_confidence"] = Confidence.MEDIUM
        duplicate = any(e.path == link.client.path and e.specifier == f"HTTP {link.client.url}" for e in bucket["evidence"])
        if not duplicate and len(bucket["evidence"]) < MAX_EVIDENCE:
            bucket["evidence"].append(EdgeEvidence(
                path=link.client.path, node_id=node_id(link.client.path), line=link.client.line,
                specifier=f"HTTP {link.client.url}", target=f"route {link.server.url} ({link.server.path}:{link.server.line})",
            ))
    connections = [_connection(source, target, "component", data) for (source, target), data in internal.items()]
    connections += [_connection(source, target, "external", data) for (source, target), data in external.items()]
    externals = [
        External(id=f"x-{category}", category=category, name=EXTERNAL_CATEGORIES[category], services=[name for name, _ in counts.most_common(6)])
        for category, counts in services.items()
    ]
    connections.sort(key=lambda c: (-c.import_count, c.id))
    return connections, sorted(externals, key=lambda e: e.name)


def _add(bucket: dict, path: str, record: ImportRecord, target: str) -> None:
    bucket["imports"] += 1
    bucket["files"].add(path)
    bucket["kinds"].add(record.kind)
    if len(bucket["evidence"]) < MAX_EVIDENCE:
        bucket["evidence"].append(EdgeEvidence(path=path, node_id=node_id(path), line=record.line, specifier=record.specifier, target=target))


def _connection(source: str, target: str, target_type: str, data: dict) -> Connection:
    only_dynamic = data["kinds"] <= {"dynamic"}
    if data["kinds"] == {"http"}:  # inferred from matching URL paths, never proven statically
        confidence = data.get("http_confidence", Confidence.LOW)
    else:
        confidence = Confidence.MEDIUM if only_dynamic else Confidence.HIGH
    return Connection(
        id=f"{source}->{target}",
        source=source,
        target=target,
        target_type=target_type,
        import_count=data["imports"],
        file_count=len(data["files"]),
        kinds=sorted(data["kinds"]),
        confidence=confidence,
        evidence=data["evidence"],
    )


# ---------------------------------------------------------------- frameworks & notes


def _frameworks(facts: dict[str, _FileFacts], packages: list[Package]) -> list[Framework]:
    importing: dict[str, set[str]] = defaultdict(set)
    roles: dict[str, str] = {}
    for path, fact in facts.items():
        for package, _record, full in fact.externals:
            signal = role_signal(package, full)
            if signal:
                roles[signal[1]] = signal[0]
                importing[signal[1]].add(path)
    declared: dict[str, set[str]] = defaultdict(set)
    for package in packages:
        for dependency, manifest in package.dependencies.items():
            signal = role_signal(dependency)
            if signal:
                roles[signal[1]] = signal[0]
                declared[signal[1]].add(manifest)
    result = []
    for name in set(importing) | set(declared):
        files, manifests = len(importing[name]), sorted(declared[name])
        confidence = Confidence.HIGH if files and manifests else Confidence.MEDIUM if files else Confidence.LOW
        result.append(Framework(name=name, role=roles[name], confidence=confidence, importing_files=files, declared_in=manifests))
    return sorted(result, key=lambda f: (-f.importing_files, f.name))


def _notes(
    summary: ArchitectureSummary, languages: Counter, components: list[Component], budget_skipped: int = 0, stuck_files: int = 0
) -> list[str]:
    notes = [
        "Components are folders grouped by package boundaries; roles are inferred from imports of known "
        "frameworks, file types and naming conventions. Low-confidence roles rest on folder names only.",
        "Connections are static imports found by parsing (Python ast, tree-sitter for JS/TS). "
        "Code was parsed, never run, so runtime-only wiring (dependency injection, string-based routing, "
        "HTTP calls between services) is not proven. Arrows marked 'http' are inferred by matching URL "
        "paths the client uses to routes the server declares.",
    ]
    unanalyzed = [lang for lang in languages if lang not in ("Python", "JavaScript", "TypeScript")]
    if unanalyzed:
        notes.append(f"Imports in {', '.join(sorted(unanalyzed)[:6])} are not analyzed yet; those files appear in components without connections.")
    if summary.dynamic_unknown:
        notes.append(f"{summary.dynamic_unknown} dynamic import(s) use computed targets and could not be resolved statically.")
    if summary.unresolved_imports:
        notes.append(f"{summary.unresolved_imports} relative import(s) point to files that are not in the archive (or were excluded).")
    if budget_skipped:
        notes.insert(0, f"Partial map: parsing stopped at the time budget and {budget_skipped:,} source files were not "
                     "parsed. Their components appear, but some connections may be missing.")
    if stuck_files:
        notes.append(f"{stuck_files} file(s) could not be parsed within the per-file time limit and were skipped.")
    if summary.skipped_too_large:
        notes.append(f"{summary.skipped_too_large} file(s) larger than {MAX_PARSE_BYTES // 1024} KB were not parsed.")
    return notes
