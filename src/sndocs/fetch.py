from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

REMOTE_URL = "https://github.com/ServiceNow/ServiceNowDocs.git"

#: The closed set of upstream branches that are release families, as opposed to
#: non-family branches (`store`, `mobile`, `main`, ...) that must never be
#: fetched as a documentation corpus.
RELEASE_FAMILIES = ("xanadu", "yokohama", "zurich", "australia", "brazil")

#: Fixed default release family — not upstream's own default branch, so a user
#: who specifies nothing never silently gets an Early Availability corpus.
DEFAULT_RELEASE = "australia"


class FetchObserver:
    """Progress and verbosity hooks for `fetch_repo`, defaulting to silence.

    `sndocs.cli` passes a subclass backed by the shared `Reporter` (issue #50)
    so a `fetch` run shows an elapsed-timer spinner while it clones or updates,
    lets git write its own progress to stderr at `-v`, and logs the exact git
    command lines at `-vv`. Direct callers and tests get this no-op base and see
    nothing. Keeping the protocol here means `sndocs.fetch` never imports `rich`
    or `sndocs.reporter` (ADR 0004), mirroring `sndocs.build.BuildObserver`."""

    #: True to drop ``--quiet`` from the git invocations so git's own transfer
    #: progress reaches stderr — set at `-v` and above.
    surfaces_git_output: bool = False

    #: True to echo each git command line through `command` before it runs —
    #: set at `-vv`.
    logs_commands: bool = False

    @contextmanager
    def phase(self, label: str) -> Iterator[None]:
        """Wrap the whole clone-or-update in an indeterminate spinner with an
        elapsed timer. `label` is ``cloning`` or ``updating``."""
        yield

    def command(self, argv: list[str]) -> None:
        """Surface one git command line about to run. Only called when
        `logs_commands` is true — i.e. at `-vv`."""

    def default_branch_resolved(self, branch: str) -> None:
        """Called with upstream's current default branch when
        `fetch_repo(report_default_branch=True)` successfully resolves it, before
        the clone/update starts. This is visibility only (issue #61): it never
        changes `branch`, the release actually being fetched."""

    def default_branch_lookup_failed(self, error: Exception) -> None:
        """Called instead of `default_branch_resolved` when that live lookup
        fails (e.g. the remote is unreachable). `fetch_repo` swallows the
        error and continues with the fixed default branch regardless — this
        hook is how the failure gets surfaced rather than silently dropped."""


def resolve_upstream_default_branch(remote_url: str) -> str:
    """Resolves `remote_url`'s current default branch — the branch its HEAD
    symref points at — via `git ls-remote --symref <remote_url> HEAD`.

    Raises `subprocess.CalledProcessError` if the remote can't be reached, and
    `RuntimeError` if it responds but without the expected HEAD symref line."""
    result = subprocess.run(
        ["git", "ls-remote", "--symref", remote_url, "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("ref:"):
            return line.split("\t", 1)[0].removeprefix("ref: refs/heads/")
    raise RuntimeError(f"no HEAD symref in `git ls-remote --symref` output for {remote_url!r}")


def fetch_repo(
    dest: Path,
    remote_url: str | None = None,
    branch: str = DEFAULT_RELEASE,
    *,
    observer: FetchObserver | None = None,
    report_default_branch: bool = False,
) -> None:
    """Shallow-clone `branch` of `remote_url` into `dest`, or update it in place if `dest`
    is already a clone.

    `observer` receives the spinner / verbosity hooks (issue #50); the default
    no-op `FetchObserver` keeps the operation silent for direct callers.

    `report_default_branch` additionally resolves and reports upstream's actual
    current default branch via `observer.default_branch_resolved` — visibility
    only (issue #61); it never changes which branch is fetched. A failed lookup
    is routed to `observer.default_branch_lookup_failed` instead of raising, so
    it never fails the fetch itself."""
    observer = observer if observer is not None else FetchObserver()
    remote_url = remote_url if remote_url is not None else REMOTE_URL

    if report_default_branch:
        try:
            upstream_default = resolve_upstream_default_branch(remote_url)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            observer.default_branch_lookup_failed(exc)
        else:
            observer.default_branch_resolved(upstream_default)

    if (dest / ".git").is_dir():
        with observer.phase("updating"):
            _update(dest, remote_url, branch, observer)
    else:
        with observer.phase("cloning"):
            _clone(dest, remote_url, branch, observer)


def _clone(dest: Path, remote_url: str, branch: str, observer: FetchObserver) -> None:
    _run(
        observer,
        ["git", "clone", *_quiet(observer), "--branch", branch, "--single-branch", "--depth", "1", remote_url, str(dest)],
    )


def _update(dest: Path, remote_url: str, branch: str, observer: FetchObserver) -> None:
    _run(observer, ["git", "remote", "set-url", "origin", remote_url], cwd=dest)
    _run(observer, ["git", "fetch", *_quiet(observer), "--depth", "1", "origin", branch], cwd=dest)
    _run(observer, ["git", "reset", *_quiet(observer), "--hard", "FETCH_HEAD"], cwd=dest)


def _quiet(observer: FetchObserver) -> list[str]:
    """``["--quiet"]`` normally, empty once the observer wants git's own output
    through (`-v` and above)."""
    return [] if observer.surfaces_git_output else ["--quiet"]


def _run(observer: FetchObserver, argv: list[str], *, cwd: Path | None = None) -> None:
    if observer.logs_commands:
        observer.command(argv)
    subprocess.run(argv, cwd=cwd, check=True)
