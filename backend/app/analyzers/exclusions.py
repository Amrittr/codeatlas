"""Exclusion policy: decides which archive paths are not extracted or analyzed, and why.

Rules are evaluated in this order. The first rule that decides wins:

1. Archive metadata (``__MACOSX/``) is always excluded.
2. Custom *include* patterns force a path to be analyzed. They override everything below.
3. Custom *exclude* patterns.
4. Default folder-name rules (dependencies, VCS, virtualenvs, caches), when enabled.
5. ``.gitignore`` files found in the project, when enabled. Nested files apply to their own
   folder. A deeper file overrides a shallower one, and the last matching line wins, so
   ``!negation`` works the way it does in git.

Custom patterns use gitignore syntax and are matched against the full path from the
archive root. As in git, once a folder is excluded nothing inside it is examined, so an
include pattern cannot re-include a file inside an excluded folder. Include the folder.

Excluded entries still appear in the tree, each with the rule that excluded it, so users
can see what was not analyzed. Build-output folders such as ``dist`` or ``target`` are not
excluded by default: some projects commit meaningful files there. They are classified as
``generated`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pathspec import GitIgnoreSpec

MAX_PATTERNS = 100
MAX_PATTERN_LENGTH = 256
MAX_GITIGNORE_BYTES = 256 * 1024
MAX_GITIGNORE_FILES = 500

ARCHIVE_METADATA_RULES: dict[str, str] = {
    "__MACOSX": "archive_metadata",
}

DEFAULT_EXCLUSION_RULES: dict[str, str] = {
    ".git": "version_control",
    ".hg": "version_control",
    ".svn": "version_control",
    "node_modules": "dependencies",
    "bower_components": "dependencies",
    "jspm_packages": "dependencies",
    ".venv": "virtual_environment",
    "venv": "virtual_environment",
    "__pypackages__": "dependencies",
    "__pycache__": "cache",
    ".mypy_cache": "cache",
    ".pytest_cache": "cache",
    ".ruff_cache": "cache",
    ".tox": "cache",
    ".nox": "cache",
    ".gradle": "cache",
    ".parcel-cache": "cache",
    ".turbo": "cache",
    ".next": "build_cache",
    ".nuxt": "build_cache",
    ".svelte-kit": "build_cache",
}

REASON_LABELS: dict[str, str] = {
    "archive_metadata": "Archive metadata created by macOS, not part of the project",
    "version_control": "Version-control internals",
    "dependencies": "Installed third-party dependencies",
    "virtual_environment": "Python virtual environment",
    "cache": "Tool cache",
    "build_cache": "Framework build cache",
    "gitignore": "Ignored by .gitignore",
    "custom": "Excluded by a custom rule",
}


class PatternError(ValueError):
    """A user-supplied pattern list is invalid. The message is safe to show the user."""


@dataclass(frozen=True, slots=True)
class ExclusionMatch:
    reason: str
    rule: str


def parse_pattern_text(text: str, *, label: str) -> list[str]:
    """Split newline-separated gitignore-style patterns. Blank and ``#`` comment lines are dropped."""
    patterns = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if len(line) > MAX_PATTERN_LENGTH:
            raise PatternError(f"{label}: a pattern is longer than {MAX_PATTERN_LENGTH} characters.")
        if "\x00" in line:
            raise PatternError(f"{label}: patterns cannot contain NUL characters.")
        patterns.append(line)
    if len(patterns) > MAX_PATTERNS:
        raise PatternError(f"{label}: at most {MAX_PATTERNS} patterns are allowed.")
    return patterns


def _compile(patterns: list[str], label: str) -> GitIgnoreSpec | None:
    if not patterns:
        return None
    try:
        return GitIgnoreSpec.from_lines(patterns)
    except (ValueError, TypeError) as error:
        raise PatternError(f"{label}: invalid pattern ({error}).") from None


@dataclass
class _GitignoreFile:
    source: str
    spec: GitIgnoreSpec
    line_numbers: list[int]


@dataclass
class ExclusionPolicy:
    apply_default_rules: bool = True
    respect_gitignore: bool = True
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._name_rules = dict(DEFAULT_EXCLUSION_RULES) if self.apply_default_rules else {}
        self._exclude = _compile(self.exclude_patterns, "Exclude patterns")
        self._include = _compile(self.include_patterns, "Include patterns")
        self._gitignores: dict[tuple[str, ...], _GitignoreFile] = {}
        self._directory_cache: dict[tuple[str, ...], ExclusionMatch | None] = {}

    @property
    def gitignore_sources(self) -> list[str]:
        return sorted(item.source for item in self._gitignores.values())

    def add_gitignore(self, directory: tuple[str, ...], text: str) -> int:
        """Register the rules of ``<directory>/.gitignore``. Returns the number of patterns."""
        lines: list[str] = []
        line_numbers: list[int] = []
        for number, raw in enumerate(text.splitlines(), start=1):
            line = raw.rstrip("\r")
            if not line.strip() or line.startswith("#"):
                continue
            lines.append(line)
            line_numbers.append(number)
        if not lines:
            return 0
        try:
            spec = GitIgnoreSpec.from_lines(lines)
        except (ValueError, TypeError):
            return 0
        source = "/".join((*directory, ".gitignore"))
        self._gitignores[directory] = _GitignoreFile(source=source, spec=spec, line_numbers=line_numbers)
        self._directory_cache.clear()
        return len(lines)

    def first_excluded(self, parts: tuple[str, ...], is_directory: bool) -> tuple[int, ExclusionMatch] | None:
        """Return ``(index, match)`` for the shallowest excluded component of ``parts``, if any."""
        for index in range(len(parts) - 1):
            match = self._directory_match(parts[: index + 1])
            if match is not None:
                return index, match
        match = self._directory_match(parts) if is_directory else self.match(parts, False)
        return (len(parts) - 1, match) if match is not None else None

    def _directory_match(self, parts: tuple[str, ...]) -> ExclusionMatch | None:
        if parts not in self._directory_cache:
            self._directory_cache[parts] = self.match(parts, True)
        return self._directory_cache[parts]

    def match(self, parts: tuple[str, ...], is_directory: bool) -> ExclusionMatch | None:
        """Decide for one path, assuming its parent folders are not excluded."""
        name = parts[-1]
        if is_directory and name in ARCHIVE_METADATA_RULES:
            return ExclusionMatch(ARCHIVE_METADATA_RULES[name], f"always excluded: {name}/")

        path = "/".join(parts) + ("/" if is_directory else "")
        if self._include is not None and self._include.match_file(path):
            return None
        if self._exclude is not None:
            result = self._exclude.check_file(path)
            if result.include:
                return ExclusionMatch("custom", f"custom rule: {self._exclude.patterns[result.index].pattern}")
        if is_directory and name in self._name_rules:
            return ExclusionMatch(self._name_rules[name], f"default rule: {name}/")
        if self.respect_gitignore and self._gitignores:
            return self._gitignore_match(parts, is_directory)
        return None

    def _gitignore_match(self, parts: tuple[str, ...], is_directory: bool) -> ExclusionMatch | None:
        decision: tuple[bool, _GitignoreFile, int] | None = None
        for depth in range(len(parts)):  # .gitignore files in every ancestor folder, shallow to deep
            gitignore = self._gitignores.get(parts[:depth])
            if gitignore is None:
                continue
            relative = "/".join(parts[depth:]) + ("/" if is_directory else "")
            result = gitignore.spec.check_file(relative)
            if result.include is not None:
                decision = (result.include, gitignore, result.index)
        if decision is None or not decision[0]:
            return None
        _, gitignore, index = decision
        pattern = gitignore.spec.patterns[index].pattern
        return ExclusionMatch("gitignore", f"{gitignore.source} line {gitignore.line_numbers[index]}: {pattern}")
