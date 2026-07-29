from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_deployment.py"
SPEC = importlib.util.spec_from_file_location("verify_deployment", SCRIPT)
assert SPEC and SPEC.loader
verify_deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_deployment)


class Response:
    status = 200
    headers = {"Content-Type": "text/plain"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return b"ok"


def test_request_sets_verifier_user_agent_and_preserves_headers(monkeypatch):
    captured = {}

    class Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    monkeypatch.setattr(
        verify_deployment.urllib.request,
        "build_opener",
        lambda *_handlers: Opener(),
    )

    status, headers, body = verify_deployment.request(
        "https://preview.sndocs.com/australia/pagefind/pagefind.js",
        headers={"Range": "bytes=0-31"},
    )

    request_headers = {
        name.lower(): value for name, value in captured["request"].header_items()
    }
    assert request_headers["user-agent"] == verify_deployment.USER_AGENT
    assert request_headers["range"] == "bytes=0-31"
    assert captured["timeout"] == 30
    assert status == 200
    assert headers == Response.headers
    assert body == b"ok"
