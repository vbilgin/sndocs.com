from __future__ import annotations

import subprocess
from pathlib import Path


def clone_family(repository: str, family: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git", "clone", "--depth", "1", "--single-branch", "--branch", family,
            f"https://github.com/{repository}.git", str(destination),
        ],
        check=True,
    )
