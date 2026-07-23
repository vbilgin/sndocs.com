from __future__ import annotations

import re
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Protocol

from .models import Settings


class SourceRepository(Protocol):
    def read_llms(self, settings: Settings) -> str: ...

    def resolve_shas(self, settings: Settings, families: list[str]) -> dict[str, str]: ...

    def materialize(self, settings: Settings, family: str, sha: str, destination: Path) -> None: ...


class RemoteSource:
    def read_llms(self, settings: Settings) -> str:
        url = f"https://raw.githubusercontent.com/{settings.repository}/HEAD/{settings.llms_path}"
        request = urllib.request.Request(url, headers={"User-Agent": "sndocs-pipeline"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8")

    def resolve_shas(self, settings: Settings, families: list[str]) -> dict[str, str]:
        remote = f"https://github.com/{settings.repository}.git"
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

    def materialize(self, settings: Settings, family: str, sha: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git", "clone", "--depth", "1", "--single-branch", "--branch", family,
                f"https://github.com/{settings.repository}.git", str(destination),
            ],
            check=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
        actual = _git(destination, "rev-parse", "HEAD")
        if actual != sha:
            raise RuntimeError(f"upstream branch {family} changed during the build; rerun discovery")


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _github_repository(url: str) -> str | None:
    match = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else None


class LocalSource:
    def __init__(self, path: Path, settings: Settings, refresh: bool = False):
        self.path = path.resolve()
        try:
            if _git(self.path, "rev-parse", "--is-inside-work-tree") != "true":
                raise ValueError(f"local source is not a Git working tree: {self.path}")
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            raise ValueError(f"local source is not a Git working tree: {self.path}") from error
        if _git(self.path, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError(f"local source repository must be clean: {self.path}")
        self.remote = self._matching_remote(settings.repository)
        if refresh:
            subprocess.run(
                ["git", "-C", str(self.path), "fetch", "--prune", self.remote],
                check=True,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
        self.default_ref = self._default_ref()

    def _matching_remote(self, expected: str) -> str:
        matches: list[str] = []
        for remote in _git(self.path, "remote").splitlines():
            urls = _git(self.path, "remote", "get-url", "--all", remote).splitlines()
            if any(_github_repository(url) == expected for url in urls):
                matches.append(remote)
        if len(matches) != 1:
            detail = "no matching remote" if not matches else f"ambiguous matching remotes: {', '.join(matches)}"
            raise ValueError(f"local source must have exactly one remote for {expected} ({detail})")
        return matches[0]

    def _default_ref(self) -> str:
        ref = f"refs/remotes/{self.remote}/HEAD"
        try:
            return _git(self.path, "symbolic-ref", ref)
        except subprocess.CalledProcessError as error:
            raise ValueError(
                f"local source has no default-branch metadata at {ref}; run `sndocs source update PATH`"
            ) from error

    def read_llms(self, settings: Settings) -> str:
        try:
            return _git(self.path, "show", f"{self.default_ref}:{settings.llms_path}") + "\n"
        except subprocess.CalledProcessError as error:
            raise ValueError(f"{settings.llms_path} is missing from local default branch {self.default_ref}") from error

    def resolve_shas(self, settings: Settings, families: list[str]) -> dict[str, str]:
        shas: dict[str, str] = {}
        missing: list[str] = []
        for family in families:
            ref = f"refs/remotes/{self.remote}/{family}^{{commit}}"
            try:
                shas[family] = _git(self.path, "rev-parse", "--verify", ref)
            except subprocess.CalledProcessError:
                missing.append(family)
        if missing:
            raise ValueError(
                f"local source is missing family refs: {', '.join(missing)}; run `sndocs source update PATH`"
            )
        return shas

    def materialize(self, settings: Settings, family: str, sha: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=False)
        with subprocess.Popen(
            ["git", "-C", str(self.path), "archive", "--format=tar", sha],
            stdout=subprocess.PIPE,
        ) as archive:
            if archive.stdout is None:
                raise RuntimeError("git archive did not provide an output stream")
            with tarfile.open(fileobj=archive.stdout, mode="r|") as stream:
                for member in stream:
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError(f"unsafe path in source archive: {member.name}")
                    stream.extract(member, destination)
            archive.stdout.close()
            returncode = archive.wait()
            if returncode:
                raise subprocess.CalledProcessError(returncode, archive.args)


def clone_local_source(path: Path, settings: Settings) -> LocalSource:
    if path.exists():
        raise ValueError(f"clone destination already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", f"https://github.com/{settings.repository}.git", str(path)],
        check=True,
        stdout=sys.stderr,
        stderr=sys.stderr,
    )
    return LocalSource(path, settings)


def update_local_source(path: Path, settings: Settings) -> LocalSource:
    return LocalSource(path, settings, refresh=True)
