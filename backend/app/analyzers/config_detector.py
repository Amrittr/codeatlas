"""Recognises well-known configuration and project-manifest files by name and location.

A match means the file exists. It does not prove the project actively uses that tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase


@dataclass(frozen=True, slots=True)
class ConfigMatch:
    label: str
    category: str


# Exact lower-cased file names.
_EXACT: dict[str, ConfigMatch] = {
    "package.json": ConfigMatch("Node.js package manifest", "package_manifest"),
    "pyproject.toml": ConfigMatch("Python project manifest", "package_manifest"),
    "setup.py": ConfigMatch("Python setuptools script", "package_manifest"),
    "setup.cfg": ConfigMatch("Python setuptools config", "package_manifest"),
    "pipfile": ConfigMatch("Pipenv manifest", "package_manifest"),
    "cargo.toml": ConfigMatch("Rust Cargo manifest", "package_manifest"),
    "go.mod": ConfigMatch("Go module definition", "package_manifest"),
    "pom.xml": ConfigMatch("Maven project", "package_manifest"),
    "build.gradle": ConfigMatch("Gradle build script", "build"),
    "build.gradle.kts": ConfigMatch("Gradle build script (Kotlin)", "build"),
    "settings.gradle": ConfigMatch("Gradle settings", "build"),
    "settings.gradle.kts": ConfigMatch("Gradle settings (Kotlin)", "build"),
    "composer.json": ConfigMatch("PHP Composer manifest", "package_manifest"),
    "gemfile": ConfigMatch("Ruby Bundler manifest", "package_manifest"),
    "mix.exs": ConfigMatch("Elixir Mix project", "package_manifest"),
    "pubspec.yaml": ConfigMatch("Dart/Flutter manifest", "package_manifest"),
    "deno.json": ConfigMatch("Deno configuration", "package_manifest"),
    "makefile": ConfigMatch("Makefile", "build"),
    "cmakelists.txt": ConfigMatch("CMake build", "build"),
    "dockerfile": ConfigMatch("Dockerfile", "container"),
    "containerfile": ConfigMatch("Container build file", "container"),
    "docker-compose.yml": ConfigMatch("Docker Compose", "container"),
    "docker-compose.yaml": ConfigMatch("Docker Compose", "container"),
    "compose.yml": ConfigMatch("Docker Compose", "container"),
    "compose.yaml": ConfigMatch("Docker Compose", "container"),
    ".dockerignore": ConfigMatch("Docker ignore rules", "container"),
    ".gitignore": ConfigMatch("Git ignore rules", "vcs"),
    ".gitattributes": ConfigMatch("Git attributes", "vcs"),
    ".gitmodules": ConfigMatch("Git submodules", "vcs"),
    ".gitlab-ci.yml": ConfigMatch("GitLab CI pipeline", "ci"),
    ".travis.yml": ConfigMatch("Travis CI pipeline", "ci"),
    "azure-pipelines.yml": ConfigMatch("Azure Pipelines", "ci"),
    "jenkinsfile": ConfigMatch("Jenkins pipeline", "ci"),
    "tsconfig.json": ConfigMatch("TypeScript compiler config", "language"),
    "jsconfig.json": ConfigMatch("JavaScript project config", "language"),
    ".editorconfig": ConfigMatch("EditorConfig", "editor"),
    ".nvmrc": ConfigMatch("Node version pin", "runtime"),
    ".python-version": ConfigMatch("Python version pin", "runtime"),
    ".tool-versions": ConfigMatch("asdf tool versions", "runtime"),
    "tox.ini": ConfigMatch("tox test environments", "test"),
    "pytest.ini": ConfigMatch("pytest config", "test"),
    "conftest.py": ConfigMatch("pytest fixtures", "test"),
    ".coveragerc": ConfigMatch("coverage.py config", "test"),
    "phpunit.xml": ConfigMatch("PHPUnit config", "test"),
    "vercel.json": ConfigMatch("Vercel deployment config", "deployment"),
    "netlify.toml": ConfigMatch("Netlify deployment config", "deployment"),
    "render.yaml": ConfigMatch("Render deployment config", "deployment"),
    "procfile": ConfigMatch("Process declaration (Heroku-style)", "deployment"),
    "fly.toml": ConfigMatch("Fly.io deployment config", "deployment"),
    "app.yaml": ConfigMatch("App Engine config", "deployment"),
    ".env": ConfigMatch("Environment variables (may contain secrets)", "environment"),
}

# fnmatch patterns on the lower-cased file name.
_NAME_PATTERNS: list[tuple[str, ConfigMatch]] = [
    ("requirements*.txt", ConfigMatch("Python requirements", "package_manifest")),
    (".env.*", ConfigMatch("Environment variables (may contain secrets)", "environment")),
    ("dockerfile.*", ConfigMatch("Dockerfile", "container")),
    ("*.dockerfile", ConfigMatch("Dockerfile", "container")),
    (".eslintrc*", ConfigMatch("ESLint config", "lint_format")),
    ("eslint.config.*", ConfigMatch("ESLint config", "lint_format")),
    (".prettierrc*", ConfigMatch("Prettier config", "lint_format")),
    ("prettier.config.*", ConfigMatch("Prettier config", "lint_format")),
    (".stylelintrc*", ConfigMatch("Stylelint config", "lint_format")),
    ("ruff.toml", ConfigMatch("Ruff config", "lint_format")),
    (".flake8", ConfigMatch("Flake8 config", "lint_format")),
    ("mypy.ini", ConfigMatch("mypy config", "lint_format")),
    (".babelrc*", ConfigMatch("Babel config", "build")),
    ("babel.config.*", ConfigMatch("Babel config", "build")),
    ("vite.config.*", ConfigMatch("Vite config", "build")),
    ("webpack.config.*", ConfigMatch("webpack config", "build")),
    ("rollup.config.*", ConfigMatch("Rollup config", "build")),
    ("tsconfig.*.json", ConfigMatch("TypeScript compiler config", "language")),
    ("next.config.*", ConfigMatch("Next.js config", "framework")),
    ("nuxt.config.*", ConfigMatch("Nuxt config", "framework")),
    ("svelte.config.*", ConfigMatch("SvelteKit config", "framework")),
    ("astro.config.*", ConfigMatch("Astro config", "framework")),
    ("angular.json", ConfigMatch("Angular workspace config", "framework")),
    ("tailwind.config.*", ConfigMatch("Tailwind CSS config", "framework")),
    ("postcss.config.*", ConfigMatch("PostCSS config", "build")),
    ("jest.config.*", ConfigMatch("Jest config", "test")),
    ("vitest.config.*", ConfigMatch("Vitest config", "test")),
    ("playwright.config.*", ConfigMatch("Playwright config", "test")),
    ("cypress.config.*", ConfigMatch("Cypress config", "test")),
    ("karma.conf.*", ConfigMatch("Karma config", "test")),
]

# fnmatch patterns on the lower-cased relative path.
_PATH_PATTERNS: list[tuple[str, ConfigMatch]] = [
    (".github/workflows/*.yml", ConfigMatch("GitHub Actions workflow", "ci")),
    (".github/workflows/*.yaml", ConfigMatch("GitHub Actions workflow", "ci")),
    (".github/dependabot.yml", ConfigMatch("Dependabot config", "ci")),
    (".circleci/config.yml", ConfigMatch("CircleCI pipeline", "ci")),
    ("bitbucket-pipelines.yml", ConfigMatch("Bitbucket Pipelines", "ci")),
]


def detect_config(name: str, path: str) -> ConfigMatch | None:
    lowered_name = name.lower()
    if lowered_name in _EXACT:
        return _EXACT[lowered_name]
    for pattern, match in _NAME_PATTERNS:
        if fnmatchcase(lowered_name, pattern):
            return match
    lowered_path = path.lower()
    for pattern, match in _PATH_PATTERNS:
        if fnmatchcase(lowered_path, pattern):
            return match
    return None
