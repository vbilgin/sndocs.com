import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

import sndocs.fetch as fetch_module
from sndocs.cli import cli


@pytest.fixture
def stubbed_remote(monkeypatch, make_fixture_git_remote) -> Path:
    """Points sndocs.fetch.REMOTE_URL at a local fixture repo instead of GitHub."""
    remote = make_fixture_git_remote()
    monkeypatch.setattr(fetch_module, "REMOTE_URL", str(remote))
    return remote


def test_fetch_command_fresh_clones_into_sndocs_repo(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0
        assert Path(".sndocs/repo/markdown/category-one/index.md").is_file()
        assert not Path(".sndocs/repo/RELEASE_NOTES.md").exists()


def test_fetch_command_updates_existing_clone_in_place(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        first = runner.invoke(cli, ["fetch"])
        assert first.exit_code == 0

        marker = Path(".sndocs/repo/untracked-marker.txt")
        marker.write_text("still here\n")

        second = runner.invoke(cli, ["fetch"])

        assert second.exit_code == 0
        assert marker.exists()


# -- Seam 1: fetch through the Reporter (issue #50) --------------------------


@pytest.fixture
def broken_remote(monkeypatch, tmp_path: Path) -> None:
    """Points sndocs.fetch.REMOTE_URL at a path that is not a git remote, so the
    `git clone` in a bare `fetch` exits non-zero."""
    monkeypatch.setattr(fetch_module, "REMOTE_URL", str(tmp_path / "does-not-exist"))


def test_fetch_shows_a_spinner_line_and_keeps_its_summary_on_stdout(
    stubbed_remote: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        # Off a terminal the spinner degrades to plain start / done lines...
        assert "fetch: cloning..." in result.stderr
        assert "fetch: done (" in result.stderr
        # ...and the retained summary line is unchanged and on stdout.
        assert "fetch: synced to .sndocs/repo" in result.output
        assert "fetch: synced to" not in result.stderr


def test_fetch_second_run_reports_the_update_phase(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        assert runner.invoke(cli, ["fetch"]).exit_code == 0

        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        assert "fetch: updating..." in result.stderr


def test_fetch_quiet_suppresses_the_spinner_and_summary(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "-q"])

        assert result.exit_code == 0, result.output
        assert result.output == ""
        assert result.stderr == ""
        # The clone still happened.
        assert Path(".sndocs/repo/markdown/category-one/index.md").is_file()


def test_fetch_normal_run_keeps_quiet_on_the_git_invocations(stubbed_remote: Path, tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []
    real_run = fetch_module.subprocess.run

    def _spy(argv, **kwargs):
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(fetch_module.subprocess, "run", _spy)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

    assert result.exit_code == 0, result.output
    clone = next(c for c in calls if "clone" in c)
    assert "--quiet" in clone
    assert "git clone" not in result.output  # the command line is not echoed


def test_fetch_verbose_drops_quiet_and_double_verbose_logs_the_commands(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []
    real_run = fetch_module.subprocess.run

    def _spy(argv, **kwargs):
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(fetch_module.subprocess, "run", _spy)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        verbose = runner.invoke(cli, ["fetch", "-v"])
        assert verbose.exit_code == 0, verbose.output
        clone = next(c for c in calls if "clone" in c)
        assert "--quiet" not in clone
        # -v alone does not echo the command lines.
        assert "$ git clone" not in verbose.output

        calls.clear()
        Path(".sndocs/repo/untracked-marker.txt").write_text("x\n")
        double = runner.invoke(cli, ["fetch", "-vv"])
        assert double.exit_code == 0, double.output
        assert "$ git fetch" in double.stderr  # the update path, echoed verbatim
        assert not any("--quiet" in c for c in calls)


def test_fetch_git_failure_renders_a_styled_error_not_a_traceback(broken_remote: None, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code != 0
        # Caught and rendered, not propagated as an uncaught CalledProcessError.
        assert not isinstance(result.exception, subprocess.CalledProcessError)
        assert "ERROR: Fetch failed" in result.output
        assert "Traceback" not in result.output


def test_fetch_git_failure_still_exits_nonzero_with_one_error_block_under_quiet(
    broken_remote: None, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "-q"])

        assert result.exit_code != 0
        assert result.output.count("ERROR: Fetch failed") == 1


def test_fetch_git_failure_adds_a_traceback_at_double_verbose(broken_remote: None, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "-vv"])

        assert result.exit_code != 0
        assert "ERROR: Fetch failed" in result.output
        assert "Traceback" in result.output
