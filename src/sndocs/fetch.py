import subprocess
from pathlib import Path

REMOTE_URL = "https://github.com/ServiceNow/ServiceNowDocs.git"
BRANCH = "australia"


def fetch_repo(dest: Path, remote_url: str | None = None, branch: str = BRANCH) -> None:
    """Shallow-clone `branch` of `remote_url` into `dest`, or update it in place if `dest`
    is already a clone."""
    remote_url = remote_url if remote_url is not None else REMOTE_URL

    if (dest / ".git").is_dir():
        _update(dest, remote_url, branch)
    else:
        _clone(dest, remote_url, branch)


def _clone(dest: Path, remote_url: str, branch: str) -> None:
    subprocess.run(
        ["git", "clone", "--quiet", "--branch", branch, "--single-branch", "--depth", "1", remote_url, str(dest)],
        check=True,
    )


def _update(dest: Path, remote_url: str, branch: str) -> None:
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=dest, check=True)
    subprocess.run(["git", "fetch", "--quiet", "--depth", "1", "origin", branch], cwd=dest, check=True)
    subprocess.run(["git", "reset", "--quiet", "--hard", "FETCH_HEAD"], cwd=dest, check=True)
