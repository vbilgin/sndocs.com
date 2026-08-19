import shutil
from pathlib import Path

from click.testing import CliRunner

from sndocs.cli import cli

MKDOCS_CONFIG = Path(__file__).resolve().parents[2] / "mkdocs.yml"


def _seed_normalized(fixture_corpus: Path) -> None:
    """Copies the fixture corpus into .sndocs/repo/ and runs `normalize`, standing in
    for a prior `sndocs fetch` + `sndocs normalize`."""
    shutil.copytree(fixture_corpus / "markdown", Path(".sndocs/repo/markdown"))
    assert CliRunner().invoke(cli, ["normalize"]).exit_code == 0
    shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")


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


def test_build_fails_loudly_without_a_normalized_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        shutil.copy(MKDOCS_CONFIG, "mkdocs.yml")

        result = runner.invoke(cli, ["build"])

        assert result.exit_code != 0
        assert not Path(".sndocs/site").exists()
