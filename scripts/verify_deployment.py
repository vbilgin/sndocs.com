from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


USER_AGENT = (
    "Mozilla/5.0 (compatible; sndocs-deployment-verifier/1.0; "
    "+https://sndocs.com/)"
)


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    request_headers = {"User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    call = urllib.request.Request(url, method=method, headers=request_headers)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    release = json.loads(args.release.read_text(encoding="utf-8"))
    try:
        check_http(args.base_url, release, args.preview)
    except (ValueError, OSError) as error:
        print(f"acceptance failed: {error}", file=sys.stderr)
        return 1
    print(
        f"acceptance passed for {args.base_url} at {release['release_id']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
