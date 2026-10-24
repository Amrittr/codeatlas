"""Browser-level tests: real server, real uploads, real DOM. Run with `make test-e2e`."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

SCREENSHOTS = "e2e-screenshots"  # pytest-playwright cleans its own test-results/ folder


def upload(page: Page, path) -> None:
    page.set_input_files("#file-input", str(path))


def open_sample(page: Page, server_url: str, archives) -> None:
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    upload(page, archives["sample"])
    expect(page.locator("#header-title")).to_have_text("Overview", timeout=15_000)


def tree_row(page: Page, name: str):
    return page.locator(".tree-row", has=page.locator(".tree-name", has_text=re.compile(f"^{re.escape(name)}$")))


@pytest.fixture
def console_errors(page: Page):
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors


def test_upload_shows_real_statistics(page: Page, server_url, archives, console_errors):
    open_sample(page, server_url, archives)
    expect(page.locator("#header-eyebrow")).to_have_text("sample-app")
    expect(page.locator('[data-stat="Files"]')).to_contain_text("22")
    expect(page.locator('[data-stat="Folders"]')).to_contain_text("12")
    expect(page.locator('[data-stat="Folders"]')).to_contain_text("2 excluded")
    expect(page.locator('[data-stat="source"]')).to_contain_text("9")
    expect(page.locator('[data-stat="test"]')).to_contain_text("2")
    expect(page.locator('[data-warning="paths_excluded"]')).to_be_visible()
    expect(page.get_by_role("heading", name="Excluded paths")).to_be_visible()
    page.screenshot(path=f"{SCREENSHOTS}/overview.png", full_page=True)
    assert console_errors == []


def test_tree_expand_collapse_and_details(page: Page, server_url, archives, console_errors):
    open_sample(page, server_url, archives)
    page.get_by_role("button", name="File Explorer").click()
    expect(page.locator("#tree-status")).to_contain_text("22 files in 12 folders · 2 excluded")

    src = tree_row(page, "src")
    expect(src).to_have_attribute("aria-expanded", "false")
    src.locator("[data-toggle]").click()
    expect(src).to_have_attribute("aria-expanded", "true")
    expect(tree_row(page, "components")).to_be_visible()

    tree_row(page, "components").locator("[data-toggle]").click()
    tree_row(page, "Button.jsx").click()
    expect(page.locator("#details-path")).to_have_text("sample-app/src/components/Button.jsx")
    expect(page.locator("#details-panel")).to_contain_text("JavaScript")
    expect(page.locator("#details-panel")).to_contain_text("Inferred")

    page.locator("#select-parent").click()
    expect(page.locator("#details-name")).to_have_text("components")
    expect(page.locator("#details-panel")).to_contain_text("Files (all levels)")

    src.locator("[data-toggle]").click()
    expect(src).to_have_attribute("aria-expanded", "false")
    expect(tree_row(page, "Button.jsx")).to_have_count(0)

    node_modules = tree_row(page, "node_modules")
    node_modules.click()
    expect(page.locator("#details-excluded")).to_contain_text("Installed dependencies")
    expect(page.locator("#details-excluded")).to_contain_text("default rule: node_modules/")
    expect(page.locator("#details-panel")).to_contain_text("2 archive entries")
    assert console_errors == []


def test_keyboard_navigation(page: Page, server_url, archives):
    open_sample(page, server_url, archives)
    page.get_by_role("button", name="File Explorer").click()
    tree = page.get_by_role("tree", name="Project files")
    tree_row(page, "sample-app").click()
    page.keyboard.press("ArrowDown")
    expect(page.locator("#details-name")).to_have_text(".git")
    page.keyboard.press("End")
    expect(page.locator("#details-name")).to_have_text("README.md")
    page.keyboard.press("Home")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowLeft")
    expect(tree_row(page, "sample-app")).to_have_attribute("aria-expanded", "false")
    page.keyboard.press("ArrowRight")
    expect(tree_row(page, "sample-app")).to_have_attribute("aria-expanded", "true")
    expect(tree).to_be_focused()


def test_search_and_filters(page: Page, server_url, archives, console_errors):
    open_sample(page, server_url, archives)
    page.get_by_role("button", name="File Explorer").click()

    page.locator("#tree-search").fill("index")
    expect(page.locator("#tree-status")).to_have_text("2 matches")
    expect(page.locator(".tree-row.is-match")).to_have_count(2)
    page.screenshot(path=f"{SCREENSHOTS}/search.png")

    page.locator("#tree-search").fill("does-not-exist")
    expect(page.locator("#tree-empty")).to_be_visible()
    page.get_by_role("button", name="Clear filters").click()
    expect(page.locator("#tree-status")).to_contain_text("Full tree")

    page.get_by_label("Classification", exact=True).select_option("test")
    expect(page.locator("#tree-status")).to_have_text("2 matches")
    page.get_by_label("Classification", exact=True).select_option("")

    page.get_by_label("Filter by extension").click()
    page.locator('input[type="checkbox"][value=".py"]').check()
    expect(page.locator("#tree-status")).to_have_text("4 matches")
    page.locator('input[type="checkbox"][value="(none)"]').check()
    expect(page.locator("#tree-status")).to_have_text("8 matches")

    # Reveal a search result in the full tree.
    page.locator("#tree-search").fill("routes")
    expect(page.locator("#tree-status")).to_have_text("2 matches")
    tree_row(page, "routes.py").click()
    page.locator("#show-in-tree").click()
    expect(page.locator("#tree-status")).to_contain_text("Full tree")
    expect(tree_row(page, "routes.py")).to_have_attribute("aria-selected", "true")
    expect(tree_row(page, "api")).to_have_attribute("aria-expanded", "true")
    assert console_errors == []


def test_expand_all_and_collapse_all(page: Page, server_url, archives):
    open_sample(page, server_url, archives)
    page.get_by_role("button", name="File Explorer").click()
    page.get_by_role("button", name="Expand all").click()
    expect(tree_row(page, "Button.jsx")).to_be_visible()
    expect(tree_row(page, "routes.py")).to_be_visible()
    page.screenshot(path=f"{SCREENSHOTS}/explorer-expanded.png")
    page.get_by_role("button", name="Collapse all").click()
    # The archive root always stays open, so only it and its single top-level folder remain.
    expect(page.locator(".tree-row")).to_have_count(2)
    expect(tree_row(page, "sample-app")).to_have_attribute("aria-expanded", "false")


def test_overview_links_reveal_in_explorer(page: Page, server_url, archives):
    open_sample(page, server_url, archives)
    page.locator('button[title="Show sample-app/package.json in the file explorer"]').first.click()
    expect(page.locator("#header-title")).to_have_text("File Explorer")
    expect(page.locator("#details-path")).to_have_text("sample-app/package.json")


@pytest.mark.parametrize(
    ("archive", "title", "message"),
    [
        ("corrupt", "Invalid or corrupted archive", "not a valid ZIP"),
        ("traversal", "Archive rejected for safety", "outside the project folder"),
        ("not_zip", "Not a ZIP archive", ".zip archive"),
        ("large", "Archive too large", "accepts archives up to"),
    ],
)
def test_upload_errors_are_explained(page: Page, server_url, archives, archive, title, message):
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    upload(page, archives[archive])
    expect(page.locator("#upload-error")).to_be_visible()
    expect(page.locator("#upload-error-title")).to_have_text(title)
    expect(page.locator("#upload-error-message")).to_contain_text(message)
    expect(page.locator("[data-nav=explorer]")).to_be_disabled()


def test_planned_features_are_marked(page: Page, server_url):
    page.goto(server_url)
    page.get_by_role("button", name=re.compile("Dependencies")).click()
    expect(page.locator("#header-title")).to_have_text("Dependency Graph")
    expect(page.get_by_text("Not available yet")).to_be_visible()


def test_session_restore_and_discard(page: Page, server_url, archives):
    open_sample(page, server_url, archives)
    page.reload()
    expect(page.locator("#header-title")).to_have_text("Overview")
    page.get_by_role("button", name="Discard").click()
    expect(page.locator("#header-title")).to_have_text("Analyze a project")
    page.reload()
    expect(page.locator("#header-title")).to_have_text("Analyze a project")


def test_mobile_layout_has_no_horizontal_scroll(page: Page, server_url, archives):
    page.set_viewport_size({"width": 390, "height": 844})
    open_sample(page, server_url, archives)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="File Explorer").click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"{SCREENSHOTS}/mobile-explorer.png", full_page=True)


def test_gitignore_and_custom_rules_from_the_ui(page: Page, server_url, archives, console_errors):
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    page.locator("#custom-rules summary").click()
    page.locator("#exclude-patterns").fill("docs/")
    expect(page.locator("#custom-rules-count")).to_have_text("1")
    upload(page, archives["gitignore"])
    expect(page.locator("#header-title")).to_have_text("Overview", timeout=15_000)
    expect(page.get_by_text(".gitignore ×1 · 1 custom")).to_be_visible()
    expect(page.locator('[data-stat="Files"]')).to_contain_text("1 excluded")

    page.get_by_role("button", name="File Explorer").click()
    tree_row(page, "src").locator("[data-toggle]").click()
    debug = tree_row(page, "debug.log")
    expect(debug).to_have_class(re.compile("is-excluded"))
    debug.click()
    expect(page.locator("#details-excluded")).to_contain_text("repo/.gitignore line 1: *.log")
    expect(page.locator("#details-panel")).to_contain_text("Not extracted")
    tree_row(page, "docs").click()
    expect(page.locator("#details-excluded")).to_contain_text("custom rule: docs/")

    # Options are remembered for the next upload in this browser.
    page.reload()
    page.get_by_role("button", name="Analyze").click()
    expect(page.locator("#exclude-patterns")).to_have_value("docs/")
    assert console_errors == []


def test_job_progress_and_cancel(page: Page, server_url, archives):
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    upload(page, archives["slow"])
    expect(page.locator("#upload-progress")).to_have_attribute(
        "data-phase", re.compile("planning|extracting|scanning"), timeout=15_000
    )
    expect(page.locator("#progress-detail")).to_contain_text(re.compile(r"of [\d,]+ (entries|files)"))
    page.screenshot(path=f"{SCREENSHOTS}/job-progress.png")
    page.locator("#cancel-upload").click()
    expect(page.locator("#upload-error-title")).to_have_text("Analysis cancelled", timeout=15_000)
    expect(page.locator("[data-nav=explorer]")).to_be_disabled()


def test_running_job_resumes_after_reload(page: Page, server_url, archives):
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    upload(page, archives["slow"])
    expect(page.locator("#upload-progress")).to_have_attribute("data-phase", re.compile(".+"), timeout=15_000)
    page.reload()
    expect(page.locator("#upload-progress")).to_be_visible()
    expect(page.locator("#header-title")).to_have_text("Overview", timeout=60_000)
    expect(page.locator('[data-stat="Files"]')).to_contain_text("18,000")


def test_generated_folders_are_labelled(page: Page, server_url, archives, console_errors):
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    upload(page, archives["built"])
    expect(page.locator("#header-title")).to_have_text("Overview", timeout=15_000)
    card = page.locator('[data-generated="app/dist"]')
    expect(card).to_contain_text("high confidence")
    expect(card).to_contain_text("2 of 3 files are bundles, source maps or compiled output")
    expect(page.locator('[data-generated="app/build"]')).to_have_count(0)

    card.click()
    expect(page.locator("#header-title")).to_have_text("File Explorer")
    expect(tree_row(page, "dist")).to_contain_text("generated")
    expect(page.locator("#details-generated")).to_contain_text("conventional build-output folder name 'dist/'")
    assert console_errors == []


def test_100k_file_project_stays_responsive(page: Page, server_url, archives, console_errors):
    page.goto(server_url)
    expect(page.locator("#server-status")).to_contain_text("Server online")
    upload(page, archives["huge"])
    expect(page.locator("#header-title")).to_have_text("Overview", timeout=180_000)
    expect(page.locator('[data-stat="Files"]')).to_contain_text("100,000")

    started = page.evaluate("performance.now()")
    page.get_by_role("button", name="File Explorer").click()
    expect(page.locator("#tree-status")).to_contain_text("100,000 files")
    explorer_ms = page.evaluate("performance.now()") - started

    started = page.evaluate("performance.now()")
    page.locator("#tree-search").fill("file9999")
    expect(page.locator("#tree-status")).to_have_text("11 matches")
    search_ms = page.evaluate("performance.now()") - started - 200  # minus the input debounce

    page.get_by_role("button", name="Clear").click()
    page.get_by_role("button", name="Expand all").click()
    expect(page.get_by_text("Large project: expanded the first 3 levels")).to_be_visible()
    # Virtualisation: only rows near the viewport exist in the DOM, however many are expanded.
    assert page.locator(".tree-row").count() < 120
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=f"{SCREENSHOTS}/explorer-100k.png")

    print(f"\n100k UI timings: explorer {explorer_ms:.0f} ms, search {search_ms:.0f} ms")
    assert explorer_ms < 2000
    assert search_ms < 1000
    assert console_errors == []
