import http.server
import json
import shutil
import socket
import subprocess
import threading
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from sndocs.cli import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
MKDOCS_CONFIG = REPO_ROOT / "mkdocs.yml"
OVERRIDES_DIR = REPO_ROOT / "overrides"


def _seed_normalized(fixture_corpus: Path) -> None:
    """Copies the fixture corpus into .sndocs/repo/ and runs `normalize`, standing in
    for a prior `sndocs fetch` + `sndocs normalize`."""
    shutil.copytree(fixture_corpus / "markdown", Path(".sndocs/repo/markdown"))
    assert CliRunner().invoke(cli, ["normalize"]).exit_code == 0
    shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")
    shutil.copytree(OVERRIDES_DIR, "overrides")


def test_build_renders_the_fixture_corpus_into_a_static_site(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        site = Path(".sndocs/site")
        index_html = (site / "markdown" / "category-one" / "index.html").read_text()
        assert "<title>Category One" in index_html
        assert "Landing page for the category-one fixture section." in index_html

        pipe_table_html = (site / "markdown" / "category-one" / "pipe-table" / "index.html").read_text()
        assert "<title>Pipe Table Page" in pipe_table_html
        assert "<table>" in pipe_table_html


def test_build_nav_mirrors_the_source_tree_with_titles_from_front_matter(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        index_html = Path(".sndocs/site/markdown/category-one/index.html").read_text()

        # The category directory is the nav section, labelled from its index.md title
        # (not the raw "category-one" directory name), and each page is labelled from
        # its own front-matter title (not its filename).
        assert "Category One" in index_html
        assert "Pipe Table Page" in index_html
        assert "HTML Table Page" in index_html
        assert "Open Fence Page" in index_html
        # The corpus's wrapper "markdown/" directory holds no pages of its own, so it
        # does not surface as a nav section label.
        assert ">Markdown<" not in index_html


def test_build_resolves_link_rewritten_by_normalize_to_the_final_page_url(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        pipe_table_html = Path(".sndocs/site/markdown/category-one/pipe-table/index.html").read_text()
        assert 'href="../html-table/"' in pipe_table_html


def test_build_excludes_normalize_reports_from_the_published_site(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        site_files = {p.name for p in Path(".sndocs/site").rglob("*") if p.is_file()}
        assert "normalization-report.json" not in site_files
        assert "normalization-manifest.json" not in site_files


def test_build_disables_materials_built_in_search_plugin(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        assert not Path(".sndocs/site/search/search_index.json").exists()


def test_build_wires_the_pagefind_ui_widget_into_rendered_pages(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        index_html = Path(".sndocs/site/markdown/category-one/index.html").read_text()
        assert 'id="sndocs-search"' in index_html
        assert "pagefind-ui.js" in index_html
        assert "pagefind-ui.css" in index_html
        assert "PagefindUI(" in index_html


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required to drive Pagefind's search runtime the way pagefind-ui does client-side.")
def test_build_produces_a_queryable_pagefind_index(fixture_corpus: Path, tmp_path: Path) -> None:
    """Runs `sndocs build` against the fixture corpus (Seam B) and, mirroring what
    pagefind-ui does in the browser, loads the built index over HTTP with Pagefind's
    own JS runtime and issues a real search against it."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        site = Path(".sndocs/site").resolve()
        pagefind_js = site / "pagefind" / "pagefind.js"
        assert pagefind_js.is_file()

        port = _free_port()
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", port),
            lambda *args: http.server.SimpleHTTPRequestHandler(*args, directory=str(site)),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            script = f"""
            const pagefind = await import({json.dumps(str(pagefind_js))});
            await pagefind.options({{ basePath: "http://127.0.0.1:{port}/pagefind/" }});
            await pagefind.init();
            const {{ results }} = await pagefind.search("category-one fixture section");
            if (results.length === 0) throw new Error("expected at least one result");
            const data = await results[0].data();
            console.log(JSON.stringify({{ count: results.length, url: data.url }}));
            """
            proc = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert proc.returncode == 0, proc.stderr
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        finally:
            server.shutdown()
            thread.join()

        assert payload["count"] >= 1
        assert "/markdown/category-one/" in payload["url"]


def test_build_surfaces_pagefinds_own_error_message_on_indexing_failure(
    fixture_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sndocs.build as build_module

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="boom: no such wasm target")

    monkeypatch.setattr(build_module.subprocess, "run", _fake_run)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])

        assert result.exit_code != 0
        assert "boom: no such wasm target" in result.output


def test_build_fails_loudly_without_a_normalized_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")

        result = runner.invoke(cli, ["build"])

        assert result.exit_code != 0
        assert not Path(".sndocs/site").exists()
