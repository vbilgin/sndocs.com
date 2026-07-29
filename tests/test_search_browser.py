import functools
import http.server
import platform
import threading

import pytest

from sndocs.builder import build_search_index


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass


def _page(*, prefix: str, base: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="{prefix}pagefind/pagefind-component-ui.css">
  </head>
  <body>
    <pagefind-config bundle-path="./" base-url="" lang="en"></pagefind-config>
    <script>
      document.currentScript.previousElementSibling.setAttribute(
        "base-url",
        new URL("{base}", location.href).pathname
      )
    </script>
    <pagefind-modal-trigger placeholder="Search"></pagefind-modal-trigger>
    <pagefind-modal reset-on-close></pagefind-modal>
    <main class="md-content__inner">{body}</main>
    <script type="module" src="{prefix}pagefind/pagefind-component-ui.js"></script>
  </body>
</html>"""


def test_pagefind_modal_searches_body_content_from_family_and_nested_pages(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    family = tmp_path / "site" / "australia"
    target = family / "target"
    nested = family / "nested" / "page"
    target.mkdir(parents=True)
    nested.mkdir(parents=True)
    family.joinpath("index.html").write_text(
        _page(prefix="", base="./", body="<h1>Family</h1><p>Landing page</p>"),
        encoding="utf-8",
    )
    target.joinpath("index.html").write_text(
        _page(
            prefix="../",
            base="../",
            body="<h1>Target topic</h1><p>The quasarorchid phrase appears only in body text.</p>",
        ),
        encoding="utf-8",
    )
    nested.joinpath("index.html").write_text(
        _page(prefix="../../", base="../../", body="<h1>Nested page</h1>"),
        encoding="utf-8",
    )
    build_search_index(family)

    handler = functools.partial(_QuietHandler, directory=str(tmp_path / "site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with sync_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except sync_api.Error as error:
                pytest.skip(f"Chromium is unavailable: {error}")
            page = browser.new_page()
            errors = []
            failed_requests = []
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "response",
                lambda response: failed_requests.append(
                    f"{response.status} {response.url}"
                )
                if response.status >= 400
                else None,
            )

            for path, shortcut in (
                ("/australia/", None),
                ("/australia/nested/page/", "Meta+k" if platform.system() == "Darwin" else "Control+k"),
            ):
                page.goto(origin + path)
                trigger = page.get_by_role("button", name="Search")
                if shortcut:
                    page.keyboard.press(shortcut)
                else:
                    trigger.click()
                query = page.locator("pagefind-modal input")
                query.fill("quasarorchid")
                page.wait_for_timeout(1000)
                assert not errors and not failed_requests, {
                    "console": errors,
                    "responses": failed_requests,
                }
                result = page.locator("pagefind-results a[href]")
                result.first.wait_for(state="visible", timeout=10000)
                assert result.first.get_attribute("href").endswith("/australia/target/")
                query.fill("no-such-pagefind-result")
                sync_api.expect(page.locator("pagefind-summary")).to_contain_text(
                    "No results", timeout=10000
                )
                page.keyboard.press("Escape")
                sync_api.expect(query).not_to_be_visible()
                sync_api.expect(trigger).to_have_attribute("aria-expanded", "false")
                if shortcut:
                    page.keyboard.press(shortcut)
                else:
                    trigger.click()
                sync_api.expect(query).to_be_visible()
                query.fill("quasarorchid")
                result.first.wait_for(state="visible", timeout=10000)
                result.first.click()
                page.wait_for_url("**/australia/target/")

            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
