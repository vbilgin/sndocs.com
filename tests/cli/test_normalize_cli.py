import json
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

import sndocs.cli as cli_module
from sndocs.cli import cli
from sndocs.normalize import NormalizationFailed


def _seed_repo(fixture_corpus: Path) -> None:
    """Copies the fixture corpus into .sndocs/repo/, standing in for a prior `sndocs fetch`."""
    shutil.copytree(fixture_corpus / "markdown", Path(".sndocs/repo/markdown"))


def test_normalize_runs_against_fixture_corpus_without_fetch(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize"])

        assert result.exit_code == 0, result.output

        report = json.loads(Path(".sndocs/normalized/normalization-report.json").read_text())
        assert report["result"]["failed"] == 0
        assert report["result"]["total_files"] == 4

        manifest = json.loads(Path(".sndocs/normalized/normalization-manifest.json").read_text())
        paths = {entry["path"] for entry in manifest["files"]}
        assert paths == {
            "markdown/category-one/index.md",
            "markdown/category-one/pipe-table.md",
            "markdown/category-one/html-table.md",
            "markdown/category-one/open-fence.md",
        }
        assert all(entry["errors"] == [] for entry in manifest["files"])


def test_normalize_closes_open_fence_and_converts_simple_html_table(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize"])
        assert result.exit_code == 0, result.output

        normalized_dir = Path(".sndocs/normalized/markdown/category-one")

        open_fence = (normalized_dir / "open-fence.md").read_text()
        assert open_fence.count("```") == 2

        html_table = (normalized_dir / "html-table.md").read_text()
        assert "<table" not in html_table
        assert "| Column A | Column B |" in html_table


def test_normalize_rewrites_cross_file_links_against_the_corpus(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize"])
        assert result.exit_code == 0, result.output

        pipe_table = Path(".sndocs/normalized/markdown/category-one/pipe-table.md").read_text()

        assert "[HTML table page](html-table.md)" in pipe_table
        assert (
            "[missing page]"
            "(https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/category-one/does-not-exist.md)"
            in pipe_table
        )
        assert "[ServiceNow](https://www.servicenow.com)" in pipe_table


def test_normalize_output_is_idempotent(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)
        assert runner.invoke(cli, ["normalize"]).exit_code == 0

        first_pass = {
            p.relative_to(".sndocs/normalized"): p.read_text()
            for p in Path(".sndocs/normalized").rglob("*.md")
        }

        shutil.rmtree(".sndocs/repo")
        shutil.copytree(".sndocs/normalized", ".sndocs/repo", ignore=shutil.ignore_patterns("normalization-*.json"))

        second = runner.invoke(cli, ["normalize"])
        assert second.exit_code == 0, second.output

        second_pass = {
            p.relative_to(".sndocs/normalized"): p.read_text()
            for p in Path(".sndocs/normalized").rglob("*.md")
        }
        assert first_pass == second_pass


def test_normalize_fails_loudly_without_a_repo_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["normalize"])

        assert result.exit_code != 0
        assert not Path(".sndocs/normalized").exists()


# -- Seam 1: normalize through the Reporter (issue #48) -----------------------


def test_default_run_prints_the_render_preserving_repair_summary(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize"])
        assert result.exit_code == 0, result.output

        # Styled tally block, worded as mechanical cleanups — never "edited".
        assert "Repairs applied (mechanical, render-preserving)" in result.output
        assert "front matter re-serialized to canonical YAML: 4" in result.output
        assert "rectangular HTML tables converted to pipe tables: 1" in result.output
        assert "edited" not in result.output.lower()
        # The retained one-line summary is unchanged and still emitted.
        assert "files normalized into .sndocs/normalized" in result.output


def test_quiet_suppresses_the_bar_the_repair_summary_and_the_retained_line(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize", "-q"])

        assert result.exit_code == 0, result.output
        assert result.output == ""
        # The work still happened.
        assert Path(".sndocs/normalized/normalization-report.json").is_file()


def test_non_terminal_run_emits_a_plain_periodic_progress_line(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize"])
        assert result.exit_code == 0, result.output

        # e.g. `normalize: 4/4 (100%) 0:00:00` — no redrawing bar, no ANSI.
        assert re.search(r"normalize: \d+/\d+ \(\d+%\) \d+:\d{2}:\d{2}", result.output)
        assert "\x1b[" not in result.output


def test_verbose_replaces_the_bar_with_per_file_lines(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize", "-v"])
        assert result.exit_code == 0, result.output

        # One line per file (completion order under the pool is nondeterministic,
        # so assert the set, not which file lands where), counted up to [4/4].
        for name in ("index.md", "pipe-table.md", "html-table.md", "open-fence.md"):
            assert re.search(rf"normalize \[\d/4\]  markdown/category-one/{re.escape(name)}$", result.output, re.M)
        assert "normalize [4/4]  markdown/category-one/" in result.output
        assert not re.search(r"normalize: \d+/\d+ \(\d+%\)", result.output)  # no plain bar line
        assert "files normalized into" in result.output


def test_double_verbose_adds_per_file_timings(fixture_corpus: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize", "-vv"])
        assert result.exit_code == 0, result.output

        assert re.search(r"normalize \[\d/4\]  markdown/category-one/\S+\.md \(\d+ms\)", result.output)


def _boom(*_args: object, **_kwargs: object) -> None:
    raise NormalizationFailed({"result": {"failed": 3}, "output": ".sndocs/normalized"})


def test_forced_failure_renders_a_styled_error_block_not_a_traceback(
    fixture_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "normalize_corpus", _boom)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize"])

        assert result.exit_code != 0
        assert "ERROR: Normalization failed" in result.output
        assert "3 file(s) failed normalization invariants" in result.output
        assert "normalization-report.json" in result.output
        assert "Traceback" not in result.output


def test_forced_failure_at_double_verbose_adds_the_traceback(
    fixture_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "normalize_corpus", _boom)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _seed_repo(fixture_corpus)

        result = runner.invoke(cli, ["normalize", "-vv"])

        assert result.exit_code != 0
        assert "3 file(s) failed normalization invariants" in result.output
        assert "Traceback" in result.output
