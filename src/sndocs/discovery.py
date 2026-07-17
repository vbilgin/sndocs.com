from __future__ import annotations

import re
import subprocess
import urllib.request
from pathlib import PurePosixPath

from .models import Discovery, Publication, Settings

FAMILY_RE = re.compile(r'^\s*-\s+"([^"]+)"\s*:\s*"([^"]+)"', re.MULTILINE)
PUBLICATION_RE = re.compile(
    r"^- \[([^]]+)]\((https://raw\.githubusercontent\.com/[^)]+/markdown/([^/]+)/index\.md)\)",
    re.MULTILINE,
)


def raw_url(settings: Settings, branch: str | None = None) -> str:
    ref = branch or "HEAD"
    return f"https://raw.githubusercontent.com/{settings.repository}/{ref}/{settings.llms_path}"


def fetch_llms(settings: Settings, branch: str | None = None) -> str:
    request = urllib.request.Request(raw_url(settings, branch), headers={"User-Agent": "sndocs-pipeline"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def parse_llms(text: str, allowlist: tuple[str, ...] = ()) -> Discovery:
    mapped = [branch for family, branch in FAMILY_RE.findall(text) if family == branch]
    if not mapped:
        raise ValueError("llms.txt did not contain a family-to-branch mapping")
    families = [family for family in mapped if not allowlist or family in allowlist]
    if not families:
        raise ValueError("family allowlist excluded every discovered family")
    publications: list[Publication] = []
    seen: set[str] = set()
    for name, url, slug in PUBLICATION_RE.findall(text):
        if slug not in seen:
            publications.append(Publication(name=name.strip(), slug=slug, index_url=url))
            seen.add(slug)
    if not publications:
        raise ValueError("llms.txt did not contain publication index links")
    return Discovery(families=families, latest=families[0], publications=publications)


def remote_shas(repository: str, families: list[str]) -> dict[str, str]:
    remote = f"https://github.com/{repository}.git"
    proc = subprocess.run(
        ["git", "ls-remote", "--heads", remote, *[f"refs/heads/{item}" for item in families]],
        check=True,
        capture_output=True,
        text=True,
    )
    found = {PurePosixPath(ref).name: sha for sha, ref in (line.split() for line in proc.stdout.splitlines())}
    missing = set(families) - found.keys()
    if missing:
        raise RuntimeError(f"upstream branches disappeared during discovery: {', '.join(sorted(missing))}")
    return found


def discover(settings: Settings) -> Discovery:
    result = parse_llms(fetch_llms(settings), settings.family_allowlist)
    result.shas = remote_shas(settings.repository, result.families)
    return result
