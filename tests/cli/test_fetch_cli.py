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
        assert Path(".sndocs/repo/australia/markdown/category-one/index.md").is_file()
        assert not Path(".sndocs/repo/australia/RELEASE_NOTES.md").exists()


def test_fetch_command_updates_existing_clone_in_place(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        first = runner.invoke(cli, ["fetch"])
        assert first.exit_code == 0

        marker = Path(".sndocs/repo/australia/untracked-marker.txt")
        marker.write_text("still here\n")

        second = runner.invoke(cli, ["fetch"])

        assert second.exit_code == 0
        assert marker.exists()


# -- Seam 2: --release / SNDOCS_RELEASE selection, scoped repo dir (issue #60) --


def test_fetch_release_flag_clones_that_branch_into_its_own_scoped_dir(
    stubbed_remote: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "--release", "brazil"])

        assert result.exit_code == 0, result.output
        assert Path(".sndocs/repo/brazil/markdown/category-one/brazil-only.md").is_file()
        assert not Path(".sndocs/repo/australia").exists()


def test_fetch_with_nothing_specified_defaults_to_australia(stubbed_remote: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        assert Path(".sndocs/repo/australia/markdown/category-one/index.md").is_file()
        assert "fetch: synced to .sndocs/repo/australia" in result.output


def test_fetch_honours_sndocs_release_env_var_when_flag_omitted(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNDOCS_RELEASE", "brazil")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        assert Path(".sndocs/repo/brazil/markdown/category-one/brazil-only.md").is_file()
        assert not Path(".sndocs/repo/australia").exists()


def test_fetch_release_flag_overrides_sndocs_release_env_var(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNDOCS_RELEASE", "australia")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "--release", "brazil"])

        assert result.exit_code == 0, result.output
        assert Path(".sndocs/repo/brazil/markdown/category-one/brazil-only.md").is_file()
        assert not Path(".sndocs/repo/australia").exists()


def test_fetch_rejects_a_non_release_family_branch_before_any_network_call(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(fetch_module.subprocess, "run", lambda argv, **kwargs: calls.append(list(argv)))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "--release", "store"])

        assert result.exit_code != 0
        assert "store" in result.output
        assert not calls  # rejected before any git subprocess ran
        assert not Path(".sndocs").exists()


def test_fetch_rejects_a_non_release_family_sndocs_release_env_var(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNDOCS_RELEASE", "main")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code != 0
        assert "main" in result.output


def test_fetch_rerunning_for_a_release_already_on_disk_updates_it_in_place(
    stubbed_remote: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        first = runner.invoke(cli, ["fetch", "--release", "brazil"])
        assert first.exit_code == 0, first.output

        marker = Path(".sndocs/repo/brazil/untracked-marker.txt")
        marker.write_text("still here\n")

        second = runner.invoke(cli, ["fetch", "--release", "brazil"])

        assert second.exit_code == 0, second.output
        assert marker.exists()


# -- Seam 3: live upstream-default visibility (issue #61) --------------------


@pytest.fixture
def stubbed_default_branch(monkeypatch):
    """Stubs `fetch_module.resolve_upstream_default_branch` (mirroring how
    `fetch_module.REMOTE_URL` is stubbed today) so CLI tests get a
    deterministic upstream default without a live lookup."""

    def _stub(name: str = "brazil"):
        monkeypatch.setattr(fetch_module, "resolve_upstream_default_branch", lambda remote_url: name)

    return _stub


def test_fetch_with_nothing_specified_reports_upstreams_live_default_branch(
    stubbed_remote: Path, stubbed_default_branch, tmp_path: Path
) -> None:
    stubbed_default_branch("brazil")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        assert (
            "fetch: no --release given, using default `australia`; "
            "upstream's current default branch is `brazil`" in result.output
        )


def test_fetch_release_flag_does_not_perform_the_live_lookup(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    def _fail_if_called(remote_url: str) -> str:
        raise AssertionError("resolve_upstream_default_branch should not be called")

    monkeypatch.setattr(fetch_module, "resolve_upstream_default_branch", _fail_if_called)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "--release", "brazil"])

        assert result.exit_code == 0, result.output
        assert "upstream's current default branch" not in result.output


def test_fetch_sndocs_release_env_var_also_skips_the_live_lookup(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    def _fail_if_called(remote_url: str) -> str:
        raise AssertionError("resolve_upstream_default_branch should not be called")

    monkeypatch.setattr(fetch_module, "resolve_upstream_default_branch", _fail_if_called)
    monkeypatch.setenv("SNDOCS_RELEASE", "brazil")

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        assert "upstream's current default branch" not in result.output


def test_fetch_quiet_suppresses_the_default_branch_line(
    stubbed_remote: Path, stubbed_default_branch, tmp_path: Path
) -> None:
    stubbed_default_branch("brazil")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch", "-q"])

        assert result.exit_code == 0, result.output
        assert result.output == ""
        assert result.stderr == ""


def test_fetch_failed_default_branch_lookup_is_surfaced_but_fetch_still_succeeds(
    stubbed_remote: Path, tmp_path: Path, monkeypatch
) -> None:
    def _boom(remote_url: str) -> str:
        raise subprocess.CalledProcessError(128, ["git", "ls-remote", "--symref", remote_url, "HEAD"])

    monkeypatch.setattr(fetch_module, "resolve_upstream_default_branch", _boom)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["fetch"])

        assert result.exit_code == 0, result.output
        assert "could not determine upstream's current default branch" in result.output
        assert Path(".sndocs/repo/australia/markdown/category-one/index.md").is_file()


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
        assert "fetch: synced to .sndocs/repo/australia" in result.output
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
        assert Path(".sndocs/repo/australia/markdown/category-one/index.md").is_file()


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
        Path(".sndocs/repo/australia/untracked-marker.txt").write_text("x\n")
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
