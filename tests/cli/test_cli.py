from pathlib import Path

from click.testing import CliRunner

from sndocs.cli import cli


def test_cli_lists_all_subcommands() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    for name in ("fetch", "normalize", "build", "serve", "all"):
        assert name in result.output


def test_each_stub_subcommand_runs(fixture_corpus: Path) -> None:
    assert fixture_corpus.is_dir()

    # "fetch", "normalize", and "build" are implemented (see their own test files); the rest are still stubs.
    for name in ("serve", "all"):
        result = CliRunner().invoke(cli, [name])
        assert result.exit_code == 0


def test_fixture_corpus_covers_required_cases(fixture_corpus: Path) -> None:
    category = fixture_corpus / "markdown" / "category-one"

    index = (category / "index.md").read_text()
    pipe_table = (category / "pipe-table.md").read_text()
    html_table = (category / "html-table.md").read_text()
    open_fence = (category / "open-fence.md").read_text()

    assert index.startswith("---\n")
    assert "|" in pipe_table and "---" in pipe_table.split("\n\n", 1)[1]
    assert "<table>" in html_table
    assert open_fence.rstrip("\n").endswith('return "unclosed fence"')
    assert open_fence.count("```") == 1

    # Cross-file link: pipe-table.md links to html-table.md.
    assert "html-table.md" in pipe_table
