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
