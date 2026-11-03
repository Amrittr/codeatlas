"""Regenerate the README screenshots from the running app, using the demo monorepo.

Usage: backend/.venv/bin/python scripts/make_screenshots.py   (needs `make css` and Playwright Chromium)
"""

from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from tests.test_architecture import MONOREPO  # noqa: E402
from tests.zip_factory import build_zip  # noqa: E402

OUT = REPO / "docs" / "images"
TOAST_SECONDS = 5.5


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=REPO / "backend",
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
            archive = Path(folder) / "shop-monorepo.zip"
            archive.write_bytes(build_zip(MONOREPO))
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            page.goto(url)
            expect(page.locator("#server-status")).to_contain_text("Server online")
            page.set_input_files("#file-input", str(archive))
            expect(page.locator("#header-title")).to_have_text("Overview", timeout=30_000)
            page.wait_for_timeout(TOAST_SECONDS * 1000)
            page.screenshot(path=OUT / "overview.png")

            page.locator("[data-nav=architecture]").click()
            canvas = page.locator("#architecture-canvas")
            expect(canvas).to_have_attribute("data-rendered-nodes", "10")
            page.wait_for_timeout(500)
            box = canvas.bounding_box()
            title = page.locator("#architecture-details-title")
            # The preset layout is deterministic: "routes" is the left box of the second layer.
            page.mouse.click(box["x"] + box["width"] * 0.355, box["y"] + box["height"] * 0.307)
            expect(title).to_have_text("@shop/api · routes")
            page.wait_for_timeout(500)
            page.screenshot(path=OUT / "architecture-map.png")

            page.locator("[data-mode=list]").click()
            page.locator('[data-list-item="@shop/web → @shop/api (root files)"]').click()
            expect(page.locator("#connection-evidence")).to_contain_text("/api/orders")
            page.screenshot(path=OUT / "architecture-evidence.png")

            page.locator("#connection-evidence [data-evidence-link]").first.click()
            expect(page.locator("#details-path")).to_have_text("shop/apps/web/src/lib/api.ts")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / "file-explorer.png")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    for image in sorted(OUT.glob("*.png")):
        print(image.relative_to(REPO), f"{image.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
