from pathlib import Path

from conftest import run_git

from sndocs.fetch import fetch_repo


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
