import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from sndocs.cli import cli


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
