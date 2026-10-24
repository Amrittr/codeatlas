"""Detects folders that are likely build or generator output, from evidence in file names.

No file contents are read. A folder is judged by:

- **Artifact share**: the fraction of its analyzed descendant files whose names look like
  build output (minified bundles, source maps, hashed chunks, compiled files, code-generator
  output). See ``classifier.artifact_reason``.
- **Conventional names**: ``dist/``, ``coverage/``, ``.next/`` and similar are build output
  in practice. Ambiguous names (``build/``, ``target/``, ``bin/``, ``obj/``, ``out/``) count
  only with corroboration: a sibling manifest of a tool that writes there (``build.gradle`` next
  to ``build/``, ``Cargo.toml`` or ``pom.xml`` next to ``target/``, a ``.csproj`` next to
  ``bin/``), or artifact evidence inside.

Only the shallowest qualifying folder is reported. Analyzed files beneath it are reclassified
as ``generated``, with the folder's confidence and reason. Detection labels folders. It never
excludes them, because a "build" folder can still hold meaningful committed files.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

from app.analyzers.classifier import artifact_reason
from app.schemas.project import Classification, Confidence
from app.services.nodes import DirectoryRecord, FileRecord

CONVENTIONAL_OUTPUT = {
    "dist", "coverage", "htmlcov", ".next", ".nuxt", ".output", ".svelte-kit", ".docusaurus",
    ".angular", "storybook-static", "__generated__", "generated",
}
# Ambiguous names → sibling file patterns that confirm a tool writes its output there.
CORROBORATED_OUTPUT: dict[str, tuple[str, ...]] = {
    "build": ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    "target": ("cargo.toml", "pom.xml", "build.sbt"),
    "bin": ("*.csproj", "*.fsproj", "*.vbproj"),
    "obj": ("*.csproj", "*.fsproj", "*.vbproj"),
    "out": (),
}
MIN_FILES_UNNAMED_HIGH = 3
MIN_FILES_UNNAMED_MEDIUM = 5


@dataclass(frozen=True, slots=True)
class GeneratedFolder:
    node_id: str
    path: str
    confidence: Confidence
    reason: str
    file_count: int




def detect_generated_folders(
    nodes: dict[str, FileRecord | DirectoryRecord], children: dict[str, list[str]], root_id: str
) -> list[GeneratedFolder]:
    """Mark generated folders on ``nodes`` (in place), reclassify their files, and return them.

    Folders are scored bottom-up. Named rules use all descendant files. The unnamed
    artifact-share rule uses only files not already explained by a qualifying subfolder, so a
    wrapper such as ``web/`` is not flagged just because ``web/vendor/`` is. The shallowest
    qualifying folder is reported.
    """
    full: dict[str, tuple[int, int]] = {}
    residual: dict[str, tuple[int, int]] = {}
    verdicts: dict[str, tuple[Confidence, str]] = {}
    for directory_id in reversed(_directories_preorder(nodes, children, root_id)):
        full_files = full_artifacts = own_files = own_artifacts = 0
        for child_id in children[directory_id]:
            child = nodes[child_id]
            if isinstance(child, FileRecord):
                if child.excluded:
                    continue
                is_artifact = artifact_reason(child.name, child.extension) is not None
                full_files += 1
                own_files += 1
                full_artifacts += is_artifact
                own_artifacts += is_artifact
            elif not child.excluded:
                full_files += full[child_id][0]
                full_artifacts += full[child_id][1]
                if child_id not in verdicts:
                    own_files += residual[child_id][0]
                    own_artifacts += residual[child_id][1]
        full[directory_id] = (full_files, full_artifacts)
        residual[directory_id] = (own_files, own_artifacts)
        node = nodes[directory_id]
        if directory_id != root_id and not node.excluded:
            verdict = _assess(node, full[directory_id], residual[directory_id], _sibling_names(nodes, children, node))
            if verdict is not None:
                verdicts[directory_id] = verdict

    found: list[GeneratedFolder] = []
    stack = list(reversed(children.get(root_id, [])))
    while stack:
        node = nodes[stack.pop()]
        if not isinstance(node, DirectoryRecord):
            continue
        if node.id not in verdicts:
            stack.extend(reversed(children[node.id]))
            continue
        confidence, reason = verdicts[node.id]
        node.generated = True
        node.generated_confidence = confidence
        node.generated_reason = reason
        _reclassify_files(nodes, children, node, confidence)
        found.append(GeneratedFolder(node.id, node.path, confidence, reason, full[node.id][0]))
    return found


def _directories_preorder(nodes, children, root_id) -> list[str]:
    order: list[str] = []
    stack = [root_id]
    while stack:
        current = stack.pop()
        order.append(current)
        stack.extend(child for child in children.get(current, ()) if isinstance(nodes[child], DirectoryRecord))
    return order


def _sibling_names(nodes, children, node: DirectoryRecord) -> list[str]:
    return [nodes[sibling].name.lower() for sibling in children.get(node.parent_id, ()) if isinstance(nodes[sibling], FileRecord)]


def _evidence(files: int, artifacts: int) -> str:
    return f"{artifacts:,} of {files:,} files are bundles, source maps or compiled output"


def _assess(
    node: DirectoryRecord, full: tuple[int, int], residual: tuple[int, int], siblings: list[str]
) -> tuple[Confidence, str] | None:
    total, flagged = full
    if total == 0:
        return None
    name = node.name.lower()
    share = flagged / total

    named = None
    if name in CONVENTIONAL_OUTPUT:
        named = f"conventional build-output folder name '{node.name}/'"
    elif name in CORROBORATED_OUTPUT:
        marker = next(
            (sibling for sibling in siblings for pattern in CORROBORATED_OUTPUT[name] if fnmatchcase(sibling, pattern)),
            None,
        )
        if marker:
            named = f"'{node.name}/' next to {marker}, whose tool writes its output there"

    if named and share >= 0.5:
        return Confidence.HIGH, f"{named}; {_evidence(total, flagged)}"
    if named:
        return Confidence.MEDIUM, named
    if name in CORROBORATED_OUTPUT and share >= 0.3:
        return Confidence.MEDIUM, f"folder named '{node.name}/' and {_evidence(total, flagged)}"

    own_total, own_flagged = residual
    own_share = own_flagged / own_total if own_total else 0
    if own_total >= MIN_FILES_UNNAMED_HIGH and own_share >= 0.8:
        return Confidence.HIGH, _evidence(own_total, own_flagged)
    if own_total >= MIN_FILES_UNNAMED_MEDIUM and own_share >= 0.5:
        return Confidence.MEDIUM, _evidence(own_total, own_flagged)
    return None


def _reclassify_files(nodes, children, folder: DirectoryRecord, confidence: Confidence) -> None:
    reason = f"inside generated folder '{folder.path}/'"
    stack = list(children[folder.id])
    while stack:
        node = nodes[stack.pop()]
        if isinstance(node, DirectoryRecord):
            stack.extend(children[node.id])
            continue
        if node.excluded:
            continue
        if node.classification == Classification.GENERATED and node.classification_confidence == Confidence.HIGH:
            continue  # its own name is stronger evidence; keep that reason
        node.classification = Classification.GENERATED
        node.classification_confidence = confidence
        node.classification_reason = reason
