import re
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

import sndocs.cli as cli_module
import sndocs.fetch as fetch_module
from sndocs.cli import cli
from sndocs.normalize import NormalizationFailed

REPO_ROOT = Path(__file__).resolve().parents[2]
MKDOCS_CONFIG = REPO_ROOT / "mkdocs.yml"
OVERRIDES_DIR = REPO_ROOT / "overrides"


@pytest.fixture
def stubbed_remote(monkeypatch, make_fixture_git_remote) -> Path:
    """Points sndocs.fetch.REMOTE_URL at a local fixture repo instead of GitHub, so
    `all`'s fetch step clones the fixture corpus (per #7)."""
    remote = make_fixture_git_remote()
    monkeypatch.setattr(fetch_module, "REMOTE_URL", str(remote))
    return remote


def _seed_site_config() -> None:
    """Drops the repo's mkdocs.yml + overrides into the cwd, standing in for the clean
    checkout `sndocs all` is normally run from."""
    shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")
    shutil.copytree(OVERRIDES_DIR, "overrides")


def test_all_runs_the_full_pipeline_from_a_clean_checkout(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_site_config()

        result = runner.invoke(cli, ["all"])
        assert result.exit_code == 0, result.output

        # Each stage wrote its output directory, in order.
        assert Path(".sndocs/repo/markdown/category-one/index.md").is_file()
        assert Path(".sndocs/normalized/markdown/category-one/index.md").is_file()
        assert Path(".sndocs/site").is_dir()

        # The final built site is well-formed: MkDocs rendered the corpus...
        index_html = Path(".sndocs/site/markdown/category-one/index.html").read_text()
        assert "<title>Category One" in index_html
        assert "Landing page for the category-one fixture section." in index_html

        # ...and Pagefind indexed it, so it's ready for `sndocs serve`.
        assert Path(".sndocs/site/pagefind/pagefind.js").is_file()
        # `--minify` defaults on (issue #34); minify-html may drop the quotes.
        assert re.search(r'id=["\']?sndocs-search["\']?', index_html)

        # `--minify` defaults on (issue #34) and `all` forwards it to `build`.
        assert "build: minified" in result.output

        # The run signs off with its own summary line, like every sibling command.
        assert "all:" in result.output
        assert ".sndocs/site" in result.output.split("all:", 1)[1]


def test_all_runs_the_steps_in_fetch_normalize_build_order(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_site_config()

        result = runner.invoke(cli, ["all"])
        assert result.exit_code == 0, result.output

        fetch_at = result.output.index("fetch:")
        normalize_at = result.output.index("normalize:")
        build_at = result.output.index("build:")
        assert fetch_at < normalize_at < build_at


def test_all_is_a_full_rebuild_every_run(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_site_config()

        assert runner.invoke(cli, ["all"]).exit_code == 0

        # Stale droppings from a previous run must not survive into the rebuilt site.
        stale = Path(".sndocs/site/stale-page/index.html")
        stale.parent.mkdir(parents=True)
        stale.write_text("<html>stale</html>")

        result = runner.invoke(cli, ["all"])
        assert result.exit_code == 0, result.output
        assert not stale.exists()


def test_all_forwards_minify_flags_to_the_build_step(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_site_config()

        baseline = runner.invoke(cli, ["all", "--no-minify"])
        assert baseline.exit_code == 0, baseline.output
        assert "minified" not in baseline.output
        plain_bytes = sum(p.stat().st_size for p in Path(".sndocs/site").rglob("*") if p.is_file())

        result = runner.invoke(cli, ["all", "--minify", "--minify-workers", "2"])
        assert result.exit_code == 0, result.output
        assert "build: minified" in result.output
        minified_bytes = sum(p.stat().st_size for p in Path(".sndocs/site").rglob("*") if p.is_file())
        assert minified_bytes < plain_bytes


def test_all_reports_a_clear_error_when_fetch_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point fetch at a path that isn't a git remote: `git clone` exits non-zero.
    monkeypatch.setattr(fetch_module, "REMOTE_URL", str(tmp_path / "does-not-exist"))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_site_config()

        result = runner.invoke(cli, ["all"])

        assert result.exit_code != 0
        # The failing fetch step renders its own styled error and stops the
        # pipeline (issue #50) — not a raw CalledProcessError traceback.
        assert not isinstance(result.exception, subprocess.CalledProcessError)
        assert "ERROR: Fetch failed" in result.output
        assert not Path(".sndocs/normalized").exists()
        assert not Path(".sndocs/site").exists()


def test_all_stops_with_a_clear_error_when_a_step_fails(
    stubbed_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*args, **kwargs):
        raise NormalizationFailed({"result": {"failed": 2}, "output": ".sndocs/normalized"})

    monkeypatch.setattr(cli_module, "normalize_corpus", _boom)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_site_config()

        result = runner.invoke(cli, ["all"])

        assert result.exit_code != 0
        assert "2 file(s) failed normalization invariants" in result.output
        # fetch ran, but the failing normalize stopped the pipeline before build.
        assert Path(".sndocs/repo/markdown/category-one/index.md").is_file()
        assert not Path(".sndocs/site").exists()
