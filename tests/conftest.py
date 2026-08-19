import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE_CORPUS = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def fixture_corpus() -> Path:
    """Path to the handcrafted fixture corpus CLI subcommands are tested against (Seam B)."""
    return FIXTURE_CORPUS


def run_git(args: list[str], cwd: Path) -> None:
    """Runs a quiet git command, for tests that build or mutate fixture git repos."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def make_fixture_git_remote(tmp_path: Path):
    """Factory fixture: builds a local git repo standing in for ServiceNowDocs, with an
    `australia` branch (seeded from the fixture corpus) and a `store` branch (release-notes
    content that must never be fetched). Returns the repo path, usable as a `git clone` source."""

    def _make(name: str = "remote") -> Path:
        remote = tmp_path / name
        remote.mkdir()
        run_git(["init", "--quiet", "-b", "australia"], cwd=remote)
        run_git(["config", "user.email", "test@example.com"], cwd=remote)
        run_git(["config", "user.name", "Test"], cwd=remote)

        shutil.copytree(FIXTURE_CORPUS / "markdown", remote / "markdown")
        run_git(["add", "."], cwd=remote)
        run_git(["commit", "--quiet", "-m", "australia branch content"], cwd=remote)

        run_git(["checkout", "--quiet", "-b", "store"], cwd=remote)
        (remote / "RELEASE_NOTES.md").write_text("store branch only\n")
        run_git(["add", "."], cwd=remote)
        run_git(["commit", "--quiet", "-m", "store branch content"], cwd=remote)

        run_git(["checkout", "--quiet", "australia"], cwd=remote)
        return remote

    return _make
