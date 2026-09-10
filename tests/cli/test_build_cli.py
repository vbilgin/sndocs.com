import http.server
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner
from mkdocs.config import load_config

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


def test_shipped_config_enables_navigation_prune() -> None:
    """Pin `navigation.prune`: without it Material renders the whole auto-generated
    nav into every page, the O(n^2) blow-up that stops a full `australia` build
    from finishing (issue #25 / ADR 0001 finding 4). The build/nav tests above
    already run `sndocs build` with this config, so they cover non-regression."""
    config = load_config(str(MKDOCS_CONFIG))
    assert "navigation.prune" in config["theme"]["features"]


def test_build_resolves_link_rewritten_by_normalize_to_the_final_page_url(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        pipe_table_html = Path(".sndocs/site/markdown/category-one/pipe-table/index.html").read_text()
        # `--minify` is on by default (issue #34) and minify-html drops the quotes
        # around a value that doesn't need them, so match either serialisation.
        assert re.search(r'href=["\']?\.\./html-table/["\']?', pipe_table_html)


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
        # `--minify` defaults on (issue #34); minify-html may drop the quotes.
        assert re.search(r'id=["\']?sndocs-search["\']?', index_html)
        assert "pagefind-ui.js" in index_html
        assert "pagefind-ui.css" in index_html
        assert "PagefindUI(" in index_html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required to drive Pagefind's search runtime the way pagefind-ui does client-side.")
def test_build_produces_a_queryable_pagefind_index(fixture_corpus: Path, tmp_path: Path, free_port: int) -> None:
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

        port = free_port
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


# --- --minify pass (issue #32) ------------------------------------------------

SITE = Path(".sndocs/site")
NORMALIZED = Path(".sndocs/normalized")


def _tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _write_normalized_page(relative: str, title: str, body: str) -> None:
    """Drops an extra already-normalized Markdown page into `.sndocs/normalized/`
    (post-`normalize`, pre-`build`) so a test can exercise specific rendered HTML."""
    path = NORMALIZED / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\n\n{body}\n", encoding="utf-8")


def test_build_minify_flag_defaults_on(fixture_corpus: Path, tmp_path: Path) -> None:
    """Issue #34 flipped the default: a bare `sndocs build` minifies. `--no-minify`
    is now the opt-out."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        assert runner.invoke(cli, ["build", "--no-minify"]).exit_code == 0
        plain_bytes = _tree_bytes(SITE)

        assert runner.invoke(cli, ["build", "--minify"]).exit_code == 0
        explicit_minify_bytes = _tree_bytes(SITE)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        # The minify pass ran without being asked to, is reported, and produced
        # exactly what an explicit `--minify` would have.
        assert "build: minified" in result.output
        default_bytes = _tree_bytes(SITE)
        assert default_bytes < plain_bytes
        assert default_bytes == explicit_minify_bytes


def test_build_minify_shrinks_the_site_and_reports_a_tally(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        assert runner.invoke(cli, ["build", "--no-minify"]).exit_code == 0
        plain_bytes = _tree_bytes(SITE)
        plain_index = (SITE / "markdown" / "category-one" / "index.html").stat().st_size

        result = runner.invoke(cli, ["build", "--minify"])
        assert result.exit_code == 0, result.output

        assert _tree_bytes(SITE) < plain_bytes
        assert (SITE / "markdown" / "category-one" / "index.html").stat().st_size < plain_index
        # The run reports how many files it minified and how much it saved.
        assert "build: minified" in result.output
        assert "/" in result.output.split("build: minified", 1)[1].split()[0]
        assert "bytes smaller" in result.output

        # Pagefind still runs *after* the minify pass and the search widget wiring
        # survives minification.
        assert (SITE / "pagefind" / "pagefind.js").is_file()
        index_html = (SITE / "markdown" / "category-one" / "index.html").read_text()
        assert re.search(r'id=["\']?sndocs-search["\']?', index_html)
        assert "PagefindUI(" in index_html  # inline script body left intact (minify_js off)


def test_build_minify_accepts_a_worker_count(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "--minify", "--minify-workers", "2"])
        assert result.exit_code == 0, result.output
        assert "build: minified" in result.output


def test_build_rejects_minify_workers_without_minify(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "--no-minify", "--minify-workers", "4"])

        assert result.exit_code != 0
        assert "--minify-workers has no effect without --minify" in result.output
        assert not SITE.exists()


def test_build_minify_preserves_pre_block_whitespace(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    page_rel = SITE / "markdown" / "category-one" / "open-fence" / "index.html"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        assert runner.invoke(cli, ["build", "--no-minify"]).exit_code == 0
        plain_size = page_rel.stat().st_size

        assert runner.invoke(cli, ["build", "--minify"]).exit_code == 0
        page = page_rel.read_text()

        # The pass really ran on this page...
        assert page_rel.stat().st_size < plain_size
        # ...but open-fence.md's fenced code block keeps its indentation and
        # newlines inside <pre> byte-for-byte.
        pre = page[page.index("<pre") : page.index("</pre>") + len("</pre>")]
        assert '"unclosed fence"' in pre
        assert "\n    " in pre  # the 4-space body indent + its newline are intact


def test_build_minify_preserves_inline_svg_and_entity_prefixed_query_params(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>'
    )
    link = "[filtered](https://www.servicenow.com/search?q=x&sect=admin&para=intro)"
    page_rel = SITE / "markdown" / "category-one" / "minify-edge" / "index.html"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)
        _write_normalized_page(
            "markdown/category-one/minify-edge.md",
            "Minify Edge Page",
            f"An icon:\n\n{svg}\n\nA link: {link}.",
        )

        assert runner.invoke(cli, ["build", "--minify"]).exit_code == 0
        minified = page_rel.read_text()

        # The inline SVG's geometry survives the pass untouched.
        assert '<path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>' in minified
        assert "<svg" in minified and "</svg>" in minified

        # The href's query string is intact: params in order, and NOT folded into
        # the section-/pilcrow-sign characters `&sect`/`&para` name (that fold
        # would silently corrupt the URL). `&amp;`/`&` are equivalent in an
        # attribute value, so accept either separator encoding.
        href = re.search(r'href="(https://www\.servicenow\.com/search[^"]*)"', minified)
        assert href is not None, minified
        url = href.group(1)
        assert url in (
            "https://www.servicenow.com/search?q=x&sect=admin&para=intro",
            "https://www.servicenow.com/search?q=x&amp;sect=admin&amp;para=intro",
        )
        assert "§" not in url and "¶" not in url


# -- Seam 1: build + minify through the Reporter (issue #49) ------------------


def test_build_announces_each_phase_and_the_minify_bar(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "--minify"])
        assert result.exit_code == 0, result.output

        # The opaque phases are announced (plain spinner lines off a terminal)...
        for phase in ("nav walk", "MkDocs render", "Pagefind index"):
            assert f"{phase}..." in result.output, phase
        # ...and the minify pass — the one phase with countable work — shows a
        # determinate progress line instead, with count, percentage and elapsed.
        assert re.search(r"minify: \d+/\d+ \(\d+%\) \d+:\d{2}:\d{2}", result.output)


def test_build_no_minify_skips_the_minify_phase(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "--no-minify"])
        assert result.exit_code == 0, result.output

        assert "MkDocs render..." in result.output
        assert "minify..." not in result.output
        assert not re.search(r"minify: \d+/\d+", result.output)


def test_build_hides_mkdocs_and_pagefind_chatter_at_normal_verbosity(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build"])
        assert result.exit_code == 0, result.output

        # MkDocs' own INFO logging and Pagefind's stdout summary stay out of a
        # normal run.
        assert "Building documentation to directory" not in result.output
        assert "mkdocs:" not in result.output
        assert "Running Pagefind v" not in result.output
        assert "[Building search indexes]" not in result.output


def test_build_still_surfaces_mkdocs_warnings_at_normal_verbosity(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    """Hiding MkDocs' INFO chatter at normal verbosity must not also swallow a
    real diagnostic: a broken internal link still reaches the user, grouped."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)
        _write_normalized_page(
            "markdown/category-one/broken-link.md",
            "Broken Link Page",
            "See [the missing page](./does-not-exist.md).",
        )

        result = runner.invoke(cli, ["build", "--no-minify"])
        assert result.exit_code == 0, result.output

        assert "WARNING:" in result.output
        assert "does-not-exist.md" in result.output
        # Still no INFO-level chatter.
        assert "Building documentation to directory" not in result.output


def test_build_quiet_suppresses_even_mkdocs_warnings(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)
        _write_normalized_page(
            "markdown/category-one/broken-link.md",
            "Broken Link Page",
            "See [the missing page](./does-not-exist.md).",
        )

        result = runner.invoke(cli, ["build", "--no-minify", "-q"])

        assert result.exit_code == 0, result.output
        assert result.output == ""


def test_build_surfaces_mkdocs_and_pagefind_output_at_verbose(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "-v"])
        assert result.exit_code == 0, result.output

        # -v routes both through the Reporter.
        assert "mkdocs: Building documentation to directory" in result.output
        assert "Running Pagefind v" in result.output


def test_build_quiet_suppresses_the_spinners_bar_and_summary(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "-q"])

        assert result.exit_code == 0, result.output
        assert result.output == ""
        # The work still happened.
        assert (SITE / "pagefind" / "pagefind.js").is_file()


def test_build_summary_lines_are_unchanged_and_on_stdout(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "--minify"])
        assert result.exit_code == 0, result.output

        assert "build: rendered .sndocs/normalized into .sndocs/site, indexed with Pagefind" in result.output
        assert re.search(r"build: minified \d+/\d+ HTML files, \d+ bytes smaller", result.output)
        # Retained summaries go to stdout; the spinners/bar go to stderr.
        assert "build: rendered" not in result.stderr
        assert "build: minified" not in result.stderr
        assert "nav walk..." in result.stderr


def test_build_pagefind_failure_renders_a_styled_error_not_a_traceback(
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
        assert "ERROR: Build failed" in result.output
        assert "boom: no such wasm target" in result.output
        assert "Traceback" not in result.output


def test_build_pagefind_failure_adds_the_traceback_at_double_verbose(
    fixture_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sndocs.build as build_module

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(build_module.subprocess, "run", _fake_run)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)

        result = runner.invoke(cli, ["build", "-vv"])

        assert result.exit_code != 0
        assert "boom" in result.output
        assert "Traceback" in result.output


def test_build_missing_normalized_dir_renders_through_reporter_error(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")

        result = runner.invoke(cli, ["build"])

        assert result.exit_code != 0
        assert "ERROR: Build failed" in result.output
        assert ".sndocs/normalized does not exist" in result.output
        assert not SITE.exists()


def test_build_minify_skips_a_poison_html_file_without_failing(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_normalized(fixture_corpus)
        # A non-UTF-8 .html file: MkDocs copies it through verbatim as a static
        # file, and minify-html can't decode it.
        poison = NORMALIZED / "markdown" / "category-one" / "poison.html"
        poison_bytes = b"<html><body>\xff\xfe poison \x00 <p>not utf-8</body></html>"
        poison.write_bytes(poison_bytes)

        result = runner.invoke(cli, ["build", "--minify"])

        assert result.exit_code == 0, result.output
        # Left byte-for-byte as MkDocs produced it...
        assert (SITE / "markdown" / "category-one" / "poison.html").read_bytes() == poison_bytes
        # ...counted, and surfaced in the build output.
        assert "could not be minified" in result.output
        assert "poison.html" in result.output
