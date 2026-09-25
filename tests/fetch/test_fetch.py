import subprocess
from pathlib import Path

import pytest
from conftest import run_git

import sndocs.fetch as fetch_module
from sndocs.fetch import FetchObserver, fetch_repo, resolve_upstream_default_branch


def test_fresh_clone_pulls_australia_branch_only(tmp_path: Path, make_fixture_git_remote) -> None:
    remote = make_fixture_git_remote()
    dest = tmp_path / "repo"

    fetch_repo(dest, remote_url=str(remote))

    assert (dest / "markdown" / "category-one" / "index.md").exists()
    assert not (dest / "RELEASE_NOTES.md").exists()


def test_update_in_place_pulls_new_commits_without_recloning(tmp_path: Path, make_fixture_git_remote) -> None:
    remote = make_fixture_git_remote()
    dest = tmp_path / "repo"
    fetch_repo(dest, remote_url=str(remote))

    marker = dest / "untracked-marker.txt"
    marker.write_text("still here\n")

    (remote / "markdown" / "category-one" / "new-file.md").write_text("new content\n")
    run_git(["add", "."], cwd=remote)
    run_git(["commit", "--quiet", "-m", "add new file"], cwd=remote)

    fetch_repo(dest, remote_url=str(remote))

    assert (dest / "markdown" / "category-one" / "new-file.md").exists()
    assert not (dest / "RELEASE_NOTES.md").exists()
    # Proves the directory was updated in place rather than deleted and re-cloned.
    assert marker.exists()


# -- Live upstream-default visibility (issue #61) -----------------------------


class _RecordingObserver(FetchObserver):
    """Captures the `default_branch_resolved` / `default_branch_lookup_failed`
    calls `fetch_repo` makes, instead of the base class's silent no-ops."""

    def __init__(self) -> None:
        self.resolved_branch: str | None = None
        self.lookup_error: Exception | None = None

    def default_branch_resolved(self, branch: str) -> None:
        self.resolved_branch = branch

    def default_branch_lookup_failed(self, error: Exception) -> None:
        self.lookup_error = error


def test_resolve_upstream_default_branch_returns_the_branch_head_points_at(
    make_fixture_git_remote,
) -> None:
    remote = make_fixture_git_remote()
    run_git(["checkout", "--quiet", "brazil"], cwd=remote)

    assert resolve_upstream_default_branch(str(remote)) == "brazil"


def test_resolve_upstream_default_branch_raises_on_unreachable_remote(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        resolve_upstream_default_branch(str(tmp_path / "does-not-exist"))


def test_fetch_repo_reports_the_resolved_default_branch_when_requested(
    tmp_path: Path, make_fixture_git_remote
) -> None:
    remote = make_fixture_git_remote()
    dest = tmp_path / "repo"
    observer = _RecordingObserver()

    fetch_repo(dest, remote_url=str(remote), observer=observer, report_default_branch=True)

    assert observer.resolved_branch == "australia"
    assert observer.lookup_error is None
    assert (dest / "markdown" / "category-one" / "index.md").exists()


def test_fetch_repo_default_branch_lookup_failure_does_not_raise_and_fetch_still_succeeds(
    tmp_path: Path, make_fixture_git_remote, monkeypatch
) -> None:
    remote = make_fixture_git_remote()
    dest = tmp_path / "repo"
    observer = _RecordingObserver()

    def _boom(remote_url: str) -> str:
        raise subprocess.CalledProcessError(128, ["git", "ls-remote", "--symref", remote_url, "HEAD"])

    monkeypatch.setattr(fetch_module, "resolve_upstream_default_branch", _boom)

    fetch_repo(dest, remote_url=str(remote), observer=observer, report_default_branch=True)

    assert observer.resolved_branch is None
    assert isinstance(observer.lookup_error, subprocess.CalledProcessError)
    # The fetch itself still succeeded using the fixed default branch.
    assert (dest / "markdown" / "category-one" / "index.md").exists()


def test_fetch_repo_skips_the_lookup_when_not_requested(
    tmp_path: Path, make_fixture_git_remote, monkeypatch
) -> None:
    remote = make_fixture_git_remote()
    dest = tmp_path / "repo"
    observer = _RecordingObserver()

    def _fail_if_called(remote_url: str) -> str:
        raise AssertionError("resolve_upstream_default_branch should not be called")

    monkeypatch.setattr(fetch_module, "resolve_upstream_default_branch", _fail_if_called)

    fetch_repo(dest, remote_url=str(remote), observer=observer)

    assert observer.resolved_branch is None
    assert observer.lookup_error is None
