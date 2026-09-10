import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import click
import pytest
from click.testing import CliRunner, Result

from sndocs import __version__
from sndocs.cli import cli
from sndocs.normalize import NormalizationFailed
from sndocs.reporter import Reporter, Verbosity

Probe = Callable[..., tuple[Result, Reporter | None]]


@pytest.fixture
def probe() -> Iterator[Probe]:
    """Registers a hidden `_probe_context` command on `cli` for one test and
    yields a helper to invoke the CLI and read back whatever `Reporter` the
    `cli()` group left on the Click context. The command is removed afterwards so
    the shipped `cli` object is not permanently mutated."""
    captured: dict[str, Reporter | None] = {}

    @cli.command(name="_probe_context", hidden=True)
    @click.pass_context
    def _probe_context(ctx: click.Context) -> None:
        captured["reporter"] = ctx.obj

    def run(*args: str) -> tuple[Result, Reporter | None]:
        captured.clear()
        argv = list(args) if "_probe_context" in args else [*args, "_probe_context"]
        result = CliRunner().invoke(cli, argv)
        return result, captured.get("reporter")

    try:
        yield run
    finally:
        cli.commands.pop("_probe_context", None)


def test_cli_reports_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_lists_all_subcommands() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    for name in ("fetch", "normalize", "build", "serve", "all"):
        assert name in result.output


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


# -- global -v/-q/--color flags and the Reporter on the context (issue #47) ----


def test_help_lists_the_global_verbosity_and_colour_flags() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    for token in ("-v, --verbose", "-q, --quiet", "--color", "auto|always|never"):
        assert token in result.output


def test_verbose_and_quiet_together_is_a_usage_error() -> None:
    result = CliRunner().invoke(cli, ["-v", "-q", "normalize"])

    assert result.exit_code != 0
    assert "cannot be used together" in result.output


def test_verbose_and_quiet_bundled_into_one_token_is_still_a_usage_error() -> None:
    result = CliRunner().invoke(cli, ["-vq", "normalize"])

    assert result.exit_code != 0
    assert "cannot be used together" in result.output


def test_context_carries_a_reporter_at_the_default_verbosity(probe: Probe) -> None:
    result, reporter = probe()

    assert result.exit_code == 0, result.output
    assert isinstance(reporter, Reporter)
    assert reporter.verbosity is Verbosity.normal


def test_verbosity_flags_resolve_onto_the_context_reporter(probe: Probe) -> None:
    assert probe("-v")[1].verbosity is Verbosity.verbose
    assert probe("-vv")[1].verbosity is Verbosity.debug
    assert probe("-vvv")[1].verbosity is Verbosity.debug
    assert probe("-q")[1].verbosity is Verbosity.quiet


def test_global_flags_are_accepted_after_the_subcommand_name_too(probe: Probe) -> None:
    # `-vv` and `--color` sitting after the subcommand still reach the group.
    _, verbose_after = probe("_probe_context", "-vv")
    assert verbose_after.verbosity is Verbosity.debug

    _, colour_after = probe("_probe_context", "--color", "never")
    assert colour_after.console.no_color is True


def test_color_choice_reaches_the_reporter(probe: Probe) -> None:
    _, reporter = probe("--color", "never")

    assert reporter.console.no_color is True


def test_all_shares_one_reporter_across_its_child_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sndocs.cli as cli_module

    seen: list[Reporter | None] = []

    def _fake_fetch(repo_dir: Path, **_kwargs: object) -> None:
        seen.append(click.get_current_context().obj)
        Path(repo_dir).mkdir(parents=True, exist_ok=True)

    def _fake_normalize(*_args: object, **_kwargs: object) -> None:
        seen.append(click.get_current_context().obj)
        raise NormalizationFailed({"result": {"failed": 1}, "output": ".sndocs/normalized"})

    monkeypatch.setattr(cli_module, "fetch_repo", _fake_fetch)
    monkeypatch.setattr(cli_module, "normalize_corpus", _fake_normalize)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["-v", "all"])

    assert result.exit_code != 0
    assert len(seen) == 2
    assert seen[0] is seen[1]
    assert isinstance(seen[0], Reporter)
    assert seen[0].verbosity is Verbosity.verbose


def test_existing_summary_lines_and_exit_codes_are_unchanged_by_the_new_flags(
    fixture_corpus: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        shutil.copytree(fixture_corpus / "markdown", Path(".sndocs/repo/markdown"))

        plain = runner.invoke(cli, ["normalize"])
        with_flags = runner.invoke(cli, ["normalize", "-v"])

        assert plain.exit_code == 0 == with_flags.exit_code
        summary = "files normalized into"
        assert summary in plain.output
        assert summary in with_flags.output
