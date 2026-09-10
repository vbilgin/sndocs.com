import os
import re
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

import sndocs.cli as cli_module
import sndocs.serve as serve_module
from sndocs.cli import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CORPUS = REPO_ROOT / "tests" / "fixtures" / "corpus"
MKDOCS_CONFIG = REPO_ROOT / "mkdocs.yml"
OVERRIDES_DIR = REPO_ROOT / "overrides"


def _wait_until(predicate, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception:  # noqa: BLE001 - polling: any failure just means "not ready yet"
            pass
        time.sleep(0.05)
    raise AssertionError("condition not met within timeout")


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture(scope="module")
def built_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Builds the fixture corpus into a static site once (via `normalize` + `build`),
    standing in for the output of #11. Tests copy this tree into their own workdir."""
    workdir = tmp_path_factory.mktemp("built-site")
    shutil.copytree(FIXTURE_CORPUS / "markdown", workdir / ".sndocs" / "repo" / "markdown")
    shutil.copy(MKDOCS_CONFIG, workdir / "mkdocs.yml")
    shutil.copytree(OVERRIDES_DIR, workdir / "overrides")

    prev = os.getcwd()
    os.chdir(workdir)
    try:
        assert CliRunner().invoke(cli, ["normalize"]).exit_code == 0
        result = CliRunner().invoke(cli, ["build"])
        assert result.exit_code == 0, result.output
    finally:
        os.chdir(prev)
    return workdir / ".sndocs" / "site"


@pytest.fixture
def serve_workdir(built_site: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding *only* a pre-built `.sndocs/site/` — no normalized
    corpus, no `mkdocs.yml`. Anything `serve` still manages to do proves it isn't
    rebuilding."""
    shutil.copytree(built_site, tmp_path / ".sndocs" / "site")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def running_serve(serve_workdir: Path, free_port: int, monkeypatch: pytest.MonkeyPatch):
    """Runs `sndocs serve` on a free port in a background thread and yields its base
    URL, then shuts the server down cleanly."""
    port = free_port
    captured: dict[str, object] = {}
    real_make = serve_module.make_server

    def capturing_make(site_dir, prt):
        server = real_make(site_dir, prt)
        captured["server"] = server
        return server

    monkeypatch.setattr(serve_module, "make_server", capturing_make)

    holder: dict[str, object] = {}
    thread = threading.Thread(
        target=lambda: holder.__setitem__("result", CliRunner().invoke(cli, ["serve", "--port", str(port)])),
        daemon=True,
    )
    thread.start()

    base = f"http://127.0.0.1:{port}"
    _wait_until(lambda: _get(base + "/markdown/category-one/")[0] == 200)
    try:
        yield base
    finally:
        server = captured.get("server")
        if server is not None:
            server.shutdown()
        thread.join(timeout=5)


def test_serve_serves_a_rendered_page_with_working_navigation(running_serve: str) -> None:
    status, body = _get(running_serve + "/markdown/category-one/")

    assert status == 200
    assert b"<title>Category One" in body
    assert b"Landing page for the category-one fixture section." in body

    # The nav lists sibling pages by their front-matter titles and links to them;
    # follow one of those links and confirm it resolves under the served tree.
    assert b"Pipe Table Page" in body
    # The built site is minified by default (issue #34); minify-html may drop the
    # quotes around a value that doesn't need them.
    assert re.search(rb'href=["\']?pipe-table/["\']?', body)
    assert _get(running_serve + "/markdown/category-one/pipe-table/")[0] == 200


def test_serve_exposes_a_working_pagefind_search_box(running_serve: str) -> None:
    # The search widget assets and the Pagefind index runtime that actually answers
    # queries are all reachable.
    assert _get(running_serve + "/pagefind/pagefind-ui.js")[0] == 200
    assert _get(running_serve + "/pagefind/pagefind-ui.css")[0] == 200
    assert _get(running_serve + "/pagefind/pagefind.js")[0] == 200

    _, body = _get(running_serve + "/markdown/category-one/")
    assert re.search(rb'id=["\']?sndocs-search["\']?', body)
    assert b"pagefind-ui.js" in body


def test_serve_does_not_rebuild_or_watch(serve_workdir: Path, running_serve: str) -> None:
    # The workdir has no normalized corpus and no mkdocs.yml, yet serve is happy:
    # it never touches the build pipeline.
    assert not (serve_workdir / ".sndocs" / "normalized").exists()
    assert not (serve_workdir / "mkdocs.yml").exists()

    # A file dropped into the site dir after the server started is served verbatim,
    # proving serve reads straight from disk with no rebuilt or cached copy.
    (serve_workdir / ".sndocs" / "site" / "marker.txt").write_text("hand-placed\n")
    status, body = _get(running_serve + "/marker.txt")

    assert status == 200
    assert body == b"hand-placed\n"


def test_serve_fails_cleanly_without_a_built_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["serve"])

    assert result.exit_code != 0
    assert "sndocs build" in result.output


# -- Seam 1: serve through the Reporter (issue #51) ------------------------


class _FakeServer:
    """Stands in for the bound `ThreadingHTTPServer` `serve_site` hands to
    `on_ready`, so the announcement path can be exercised without a socket."""

    server_address = ("127.0.0.1", 8000)


@pytest.fixture
def instant_serve(monkeypatch: pytest.MonkeyPatch):
    """Replaces `serve_site` with a stub that fires `on_ready` once and returns —
    as if the user hit Ctrl+C the moment the server came up."""

    def _fake_serve(site_dir, port=8000, *, on_ready=None):
        if on_ready is not None:
            on_ready(_FakeServer())

    monkeypatch.setattr(cli_module, "serve_site", _fake_serve)


def test_serve_announces_the_url_on_stdout_and_signs_off(serve_workdir: Path, instant_serve: None) -> None:
    result = CliRunner().invoke(cli, ["serve"])

    assert result.exit_code == 0, result.output
    assert "serve: serving" in result.stdout
    assert "http://127.0.0.1:8000/" in result.stdout
    assert "serve: stopped" in result.stdout


def test_serve_honours_the_color_choice_and_still_announces(serve_workdir: Path, instant_serve: None) -> None:
    result = CliRunner().invoke(cli, ["serve", "--color", "never"])

    assert result.exit_code == 0, result.output
    assert "serve: serving" in result.stdout


def test_serve_quiet_suppresses_the_announcement(serve_workdir: Path, instant_serve: None) -> None:
    result = CliRunner().invoke(cli, ["serve", "-q"])

    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert result.stderr == ""


def test_serve_bind_failure_renders_a_styled_error_not_a_traceback(
    serve_workdir: Path, free_port: int
) -> None:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as occupied:
        occupied.bind(("127.0.0.1", free_port))
        occupied.listen(1)

        result = CliRunner().invoke(cli, ["serve", "--port", str(free_port)])

    assert result.exit_code != 0
    # Caught and rendered, not propagated as an uncaught OSError.
    assert not isinstance(result.exception, OSError)
    assert "ERROR: Serve failed" in result.output
    assert f"could not bind localhost:{free_port}" in result.output
    assert "Traceback" not in result.output


def test_serve_bind_failure_still_shown_under_quiet(serve_workdir: Path, free_port: int) -> None:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as occupied:
        occupied.bind(("127.0.0.1", free_port))
        occupied.listen(1)

        result = CliRunner().invoke(cli, ["serve", "--port", str(free_port), "-q"])

    assert result.exit_code != 0
    assert result.output.count("ERROR: Serve failed") == 1
