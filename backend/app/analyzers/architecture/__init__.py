"""Architecture map v1: components, roles and connections inferred from code evidence.

Pipeline (``builder.build_architecture``):

1. ``manifests``: read package.json / pyproject.toml / requirements / tsconfig as data
   (never executed) to find package boundaries, declared dependencies and path aliases.
2. ``parsers``: extract import statements from JS/TS (tree-sitter) and Python (ast).
3. ``resolver``: resolve each import to a project file, an external package, or a standard
   library or built-in module. Unresolvable relative imports are counted, not guessed.
4. ``builder``: group files into components (package boundaries, then top-level source
   folders), infer each component's role from imports of known frameworks, file types and
   naming conventions, and aggregate file-level imports into component connections.

Every role and connection carries its evidence (file, line, rule) and a confidence. A role
supported only by a folder name is labelled low confidence: a hypothesis, not a fact.
"""
