from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    call = urllib.request.Request(url, method=method, headers=headers or {})
    opener = urllib.request.build_opener(
        urllib.request.HTTPHandler(), urllib.request.HTTPSHandler()
    )
    try:
        with opener.open(call, timeout=30) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def check_http(base_url: str, release: dict, preview: bool) -> None:
    base = base_url.rstrip("/")
    latest = release["latest"]
    archived = [
        family
        for family, record in release["families"].items()
        if record["archived"]
    ]
    for path in ("/", f"/{latest}/", "/versions.json"):
        status, headers, _body = request(base + path)
        if status != 200:
            raise ValueError(f"{path} returned HTTP {status}")
        if headers.get("X-Sndocs-Release") != release["release_id"]:
            raise ValueError(f"{path} returned the wrong release ID")
        if preview and headers.get("X-Robots-Tag") != "noindex, nofollow":
            raise ValueError(f"{path} omitted the preview no-index policy")
    for family in archived:
        status, _headers, _body = request(base + f"/{family}/")
        if status != 200:
            raise ValueError(f"archived family {family} returned HTTP {status}")
    status, headers, _body = request(base + f"/{latest}", method="HEAD")
    if status != 200 and status != 308:
        raise ValueError(f"slashless family URL returned HTTP {status}")
    status, _headers, _body = request(
        base + f"/{latest}/pagefind/pagefind.js",
        headers={"Range": "bytes=0-31"},
    )
    if status != 206:
        raise ValueError(f"Pagefind range request returned HTTP {status}")
    status, _headers, _body = request(base + f"/{latest}/sndocs-acceptance-missing/")
    if status != 404:
        raise ValueError(f"missing family page returned HTTP {status}")


def check_browser(base_url: str, release: dict) -> None:
    from playwright.sync_api import sync_playwright

    latest = release["latest"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors = []
        failed_responses = []
        page.on(
            "console",
            lambda message: errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: failed_responses.append(
                f"{response.status} {response.url}"
            )
            if response.status >= 400
            else None,
        )
        page.goto(f"{base_url.rstrip('/')}/{latest}/", wait_until="networkidle")
        page.get_by_role("button", name="Search").click()
        query = page.locator("pagefind-modal input")
        query.wait_for(state="visible")
        query.fill(latest)
        page.locator("pagefind-summary").wait_for(state="visible", timeout=10000)
        if errors or failed_responses:
            raise ValueError(
                "browser acceptance reported failures: "
                f"console={errors}, responses={failed_responses}"
            )
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    release = json.loads(args.release.read_text(encoding="utf-8"))
    try:
        check_http(args.base_url, release, args.preview)
        if args.browser:
            check_browser(args.base_url, release)
    except (ValueError, OSError) as error:
        print(f"acceptance failed: {error}", file=sys.stderr)
        return 1
    print(
        f"acceptance passed for {args.base_url} at {release['release_id']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
