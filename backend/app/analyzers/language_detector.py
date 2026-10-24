"""Infers a file's language from its name or extension. Contents are never read.

``kind`` separates programming/markup/style languages (counted as source code) from data,
configuration and prose formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LanguageKind = Literal["programming", "markup", "style", "data", "config", "prose"]


@dataclass(frozen=True, slots=True)
class Language:
    name: str
    kind: LanguageKind


def _lang(name: str, kind: LanguageKind, *extensions: str) -> dict[str, Language]:
    language = Language(name, kind)
    return {ext: language for ext in extensions}


EXTENSION_LANGUAGES: dict[str, Language] = {
    **_lang("Python", "programming", ".py", ".pyi", ".pyw"),
    **_lang("JavaScript", "programming", ".js", ".mjs", ".cjs", ".jsx"),
    **_lang("TypeScript", "programming", ".ts", ".tsx", ".mts", ".cts"),
    **_lang("Java", "programming", ".java"),
    **_lang("Kotlin", "programming", ".kt", ".kts"),
    **_lang("Scala", "programming", ".scala", ".sc"),
    **_lang("Groovy", "programming", ".groovy", ".gradle"),
    **_lang("Go", "programming", ".go"),
    **_lang("Rust", "programming", ".rs"),
    **_lang("C", "programming", ".c"),
    **_lang("C/C++ Header", "programming", ".h"),
    **_lang("C++", "programming", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"),
    **_lang("C#", "programming", ".cs"),
    **_lang("Objective-C", "programming", ".m", ".mm"),
    **_lang("Swift", "programming", ".swift"),
    **_lang("PHP", "programming", ".php"),
    **_lang("Ruby", "programming", ".rb", ".rake", ".gemspec"),
    **_lang("Perl", "programming", ".pl", ".pm"),
    **_lang("Lua", "programming", ".lua"),
    **_lang("R", "programming", ".r"),
    **_lang("Dart", "programming", ".dart"),
    **_lang("Elixir", "programming", ".ex", ".exs"),
    **_lang("Erlang", "programming", ".erl", ".hrl"),
    **_lang("Haskell", "programming", ".hs"),
    **_lang("OCaml", "programming", ".ml", ".mli"),
    **_lang("Clojure", "programming", ".clj", ".cljs", ".cljc"),
    **_lang("Julia", "programming", ".jl"),
    **_lang("Zig", "programming", ".zig"),
    **_lang("Solidity", "programming", ".sol"),
    **_lang("Shell", "programming", ".sh", ".bash", ".zsh", ".fish"),
    **_lang("PowerShell", "programming", ".ps1", ".psm1"),
    **_lang("Batch", "programming", ".bat", ".cmd"),
    **_lang("SQL", "programming", ".sql"),
    **_lang("GraphQL", "programming", ".graphql", ".gql"),
    **_lang("Protocol Buffers", "programming", ".proto"),
    **_lang("HCL", "programming", ".tf", ".hcl"),
    **_lang("Jupyter Notebook", "programming", ".ipynb"),
    **_lang("HTML", "markup", ".html", ".htm"),
    **_lang("Vue", "markup", ".vue"),
    **_lang("Svelte", "markup", ".svelte"),
    **_lang("Astro", "markup", ".astro"),
    **_lang("CSS", "style", ".css"),
    **_lang("SCSS", "style", ".scss"),
    **_lang("Sass", "style", ".sass"),
    **_lang("Less", "style", ".less"),
    **_lang("JSON", "data", ".json", ".jsonc", ".json5"),
    **_lang("XML", "data", ".xml"),
    **_lang("CSV", "data", ".csv", ".tsv"),
    **_lang("YAML", "config", ".yml", ".yaml"),
    **_lang("TOML", "config", ".toml"),
    **_lang("INI", "config", ".ini", ".cfg", ".conf"),
    **_lang("Markdown", "prose", ".md", ".mdx", ".markdown"),
    **_lang("reStructuredText", "prose", ".rst"),
    **_lang("AsciiDoc", "prose", ".adoc"),
}

FILENAME_LANGUAGES: dict[str, Language] = {
    "dockerfile": Language("Dockerfile", "config"),
    "containerfile": Language("Dockerfile", "config"),
    "makefile": Language("Makefile", "programming"),
    "gnumakefile": Language("Makefile", "programming"),
    "cmakelists.txt": Language("CMake", "programming"),
    "gemfile": Language("Ruby", "programming"),
    "rakefile": Language("Ruby", "programming"),
    "jenkinsfile": Language("Groovy", "programming"),
    "vagrantfile": Language("Ruby", "programming"),
}


def detect_language(name: str, extension: str) -> Language | None:
    lowered = name.lower()
    if lowered in FILENAME_LANGUAGES:
        return FILENAME_LANGUAGES[lowered]
    if lowered.startswith("dockerfile."):
        return FILENAME_LANGUAGES["dockerfile"]
    return EXTENSION_LANGUAGES.get(extension)
