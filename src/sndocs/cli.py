import shlex
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import click

from sndocs import __version__
from sndocs.build import BuildObserver, PagefindIndexingFailed, build_site
from sndocs.fetch import FetchObserver, fetch_repo
from sndocs.minify import MinifyReport
from sndocs.normalize import (
    REPORT_FILENAME,
    NormalizationFailed,
    discover,
    normalize_corpus,
    repair_summary_lines,
)
from sndocs.reporter import Reporter, Verbosity
from sndocs.serve import DEFAULT_PORT, serve_site

REPO_DIR = Path(".sndocs") / "repo"
NORMALIZED_DIR = Path(".sndocs") / "normalized"
SITE_DIR = Path(".sndocs") / "site"
MKDOCS_CONFIG = Path("mkdocs.yml")

# Cap on per-file minify errors listed individually in the build output.
MINIFY_FAILURES_SHOWN = 10

class GlobalOptionGroup(click.Group):
    """A `click.Group` that accepts the global `-v/-q/--color` options positioned
    after the subcommand name, not just before it, by hoisting them to the front
    of the argument list before Click's own parsing runs.

    Click only parses group options *before* the subcommand name; this lets
    `sndocs normalize -v` behave like `sndocs -v normalize` (issue #47: accepted
    before and after the subcommand where practical). Which options count as
    global is read straight off `self.params`, so a new flag on `cli()` needs no
    matching edit here; `-V/--version` and `--help` are skipped as eager.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        return super().parse_args(ctx, _hoist_global_options(self, args))


def _hoist_global_options(group: click.Group, args: list[str]) -> list[str]:
    """Move this group's own options (and any value they consume) to the front of
    `args`, preserving the order of everything else. Everything from a bare `--`
    onward is left untouched."""
    valueless, valued = _global_option_names(group)
    hoisted: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            rest.extend(args[index:])
            break
        if token in valueless or any(token.startswith(f"{opt}=") for opt in valued):
            hoisted.append(token)
        elif token in valued:
            hoisted.append(token)
            if index + 1 < len(args):
                index += 1
                hoisted.append(args[index])
        elif _is_short_bundle_of(token, valueless):
            hoisted.append(token)  # -vv, -vq, ... — every char is a global flag
        else:
            rest.append(token)
        index += 1
    return hoisted + rest


def _global_option_names(group: click.Group) -> tuple[frozenset[str], frozenset[str]]:
    """The opt strings of `group`'s non-eager options, split into those that take
    no value (`-v`, `-q`) and those that do (`--color`)."""
    valueless: set[str] = set()
    valued: set[str] = set()
    for param in group.params:
        if not isinstance(param, click.Option) or param.is_eager:
            continue
        (valueless if param.is_flag or param.count else valued).update(param.opts)
    return frozenset(valueless), frozenset(valued)


def _is_short_bundle_of(token: str, valueless: frozenset[str]) -> bool:
    """True for a single-dash run like `-vv` or `-vq` whose every character is one
    of the group's valueless short options."""
    if len(token) < 2 or not token.startswith("-") or token.startswith("--"):
        return False
    return all(f"-{char}" in valueless for char in token[1:])


def minify_options(func: Callable[..., None]) -> Callable[..., None]:
    """Shared `--minify/--no-minify` + `--minify-workers` options for `build` and
    `all` (which forwards them straight through)."""
    func = click.option(
        "--minify-workers",
        type=click.IntRange(min=1),
        default=None,
        help="Parallel workers for --minify (default: available CPU count).",
    )(func)
    func = click.option(
        "--minify/--no-minify",
        default=True,
        show_default=True,
        help="Minify the rendered site's HTML with minify-html before Pagefind indexing.",
    )(func)
    return func


@click.group(cls=GlobalOptionGroup)
@click.version_option(__version__, "-V", "--version", prog_name="sndocs")
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="More detail: -v for per-item lines and subprocess output, -vv to add a "
    "formatted traceback on failure. Repeatable.",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Errors only: silence progress bars, spinners, summaries, and warnings. "
    "A failing run still exits non-zero.",
)
@click.option(
    "--color",
    type=click.Choice(["auto", "always", "never"]),
    default="auto",
    show_default=True,
    help="Colour output. 'auto' honours NO_COLOR and a non-terminal stderr; "
    "'always' keeps colour on even under NO_COLOR; 'never' forces it off. A "
    "non-terminal stderr still drops the animated bar regardless.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: int, quiet: bool, color: str) -> None:
    """Fetch, normalize, and build a local ServiceNowDocs site."""
    if verbose and quiet:
        raise click.UsageError("-v/--verbose and -q/--quiet cannot be used together.")
    ctx.obj = Reporter.for_cli(Verbosity.from_flags(verbose, quiet), color=color)


class _ReporterFetchObserver(FetchObserver):
    """Routes `fetch_repo`'s spinner / verbosity hooks through the shared
    `Reporter`: an elapsed-timer spinner over the clone-or-update, git's own
    progress from `-v` up, and the exact git command lines at `-vv`."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter

    @property
    def surfaces_git_output(self) -> bool:
        return self._reporter.shows_subprocess_output

    @property
    def logs_commands(self) -> bool:
        return self._reporter.verbosity >= Verbosity.debug

    @contextmanager
    def phase(self, label: str) -> Iterator[None]:
        with self._reporter.spinner(f"fetch: {label}", done_label="fetch"):
            yield

    def command(self, argv: list[str]) -> None:
        self._reporter.log(f"$ {shlex.join(argv)}")


@cli.command()
@click.pass_context
def fetch(ctx: click.Context) -> None:
    """Clone or update the australia branch of ServiceNowDocs into .sndocs/repo/."""
    reporter: Reporter = ctx.obj
    try:
        fetch_repo(REPO_DIR, observer=_ReporterFetchObserver(reporter))
    except subprocess.CalledProcessError as exc:
        reporter.error(
            "Fetch failed",
            f"git exited {exc.returncode} while syncing the corpus into {REPO_DIR}. "
            "Check network access to the ServiceNowDocs remote and that the "
            "directory is writable.",
        )
        reporter.print_exception(exc)
        raise SystemExit(1) from exc
    reporter.summary(f"fetch: synced to {REPO_DIR}")


@cli.command()
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=None,
    help="Parallel workers (default: available CPU count).",
)
@click.pass_context
def normalize(ctx: click.Context, workers: int | None) -> None:
    """Normalize .sndocs/repo/ into .sndocs/normalized/."""
    reporter: Reporter = ctx.obj
    if not REPO_DIR.is_dir():
        raise click.ClickException(f"{REPO_DIR} does not exist. Run `sndocs fetch` first, or populate it manually.")

    # One extra directory walk to size the bar before `normalize_corpus` starts;
    # negligible next to the per-file markdown parsing it feeds.
    total = len(discover(REPO_DIR))
    try:
        with reporter.progress("normalize", total=total) as tick:

            def on_progress(file_result: dict[str, object]) -> None:
                path = str(file_result["path"])
                if reporter.verbosity is Verbosity.debug:
                    seconds = float(file_result.get("seconds", 0.0) or 0.0)
                    tick(f"{path} ({seconds * 1000:.0f}ms)")
                elif reporter.verbosity is Verbosity.verbose:
                    tick(path)
                else:
                    tick()
                for warning in _normalize_file_warnings(file_result):
                    if reporter.verbosity >= Verbosity.verbose:
                        reporter.log(f"WARNING: {warning}")
                    else:
                        reporter.warn(warning)

            report = normalize_corpus(
                REPO_DIR, NORMALIZED_DIR, workers=workers, on_progress=on_progress
            )
    except NormalizationFailed as exc:
        failed = exc.report["result"]["failed"]
        reporter.error(
            "Normalization failed",
            f"{failed} file(s) failed normalization invariants.",
            report_path=NORMALIZED_DIR / REPORT_FILENAME,
        )
        reporter.print_exception(exc)
        raise SystemExit(1) from exc

    result = report["result"]
    reporter.details(
        "Repairs applied (mechanical, render-preserving)",
        repair_summary_lines(result["transformations"]),
    )
    reporter.flush_warnings("Warnings")
    reporter.summary(
        f"normalize: {result['succeeded']}/{result['total_files']} files normalized "
        f"into {NORMALIZED_DIR} ({result['changed_files']} changed)"
    )


def _normalize_file_warnings(file_result: dict[str, object]) -> list[str]:
    """Non-fatal notes for one normalized file: a raw HTML table that stayed raw
    because it is not a simple rectangular table, or cosmetic cleanup skipped to
    keep the rendered output identical. Neither fails the file."""
    stats = file_result.get("stats") or {}
    path = file_result["path"]
    notes: list[str] = []
    remaining = stats.get("raw_tables_remaining", 0)
    if remaining:
        notes.append(f"{path}: {remaining} raw HTML table(s) left unconverted (not a simple rectangular table)")
    if stats.get("render_changing_cleanup_rejected", 0):
        notes.append(f"{path}: cosmetic cleanup skipped to preserve the rendered output")
    return notes


class _ReporterBuildObserver(BuildObserver):
    """Routes `build_site`'s phase / minify / tool-output hooks through the shared
    `Reporter`: an elapsed-timer spinner per phase, the determinate minify bar,
    and MkDocs / Pagefind output only from `-v` up."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter

    @property
    def surfaces_tool_output(self) -> bool:
        return self._reporter.shows_subprocess_output

    @contextmanager
    def phase(self, label: str) -> Iterator[None]:
        with self._reporter.spinner(label):
            yield

    @contextmanager
    def minify_progress(self, total: int) -> Iterator[Callable[..., None]]:
        with self._reporter.progress("minify", total=total) as tick:
            yield tick

    def tool_line(self, line: str) -> None:
        self._reporter.log(line)

    def tool_warning(self, line: str) -> None:
        self._reporter.warn(line)


@cli.command()
@minify_options
@click.pass_context
def build(ctx: click.Context, minify: bool, minify_workers: int | None) -> None:
    """Build the MkDocs site from .sndocs/normalized/ into .sndocs/site/."""
    reporter: Reporter = ctx.obj
    if minify_workers is not None and not minify:
        raise click.UsageError("--minify-workers has no effect without --minify.")
    if not NORMALIZED_DIR.is_dir():
        reporter.error(
            "Build failed",
            f"{NORMALIZED_DIR} does not exist. Run `sndocs normalize` first, or populate it manually.",
        )
        raise SystemExit(1)
    try:
        report = build_site(
            NORMALIZED_DIR,
            SITE_DIR,
            MKDOCS_CONFIG,
            minify=minify,
            minify_workers=minify_workers,
            observer=_ReporterBuildObserver(reporter),
        )
    except PagefindIndexingFailed as exc:
        reporter.error("Build failed", f"Pagefind indexing failed: {exc}")
        reporter.print_exception(exc)
        raise SystemExit(1) from exc
    reporter.flush_warnings("MkDocs warnings")
    reporter.summary(f"build: rendered {NORMALIZED_DIR} into {SITE_DIR}, indexed with Pagefind")
    _report_minify(reporter, report)


def _report_minify(reporter: Reporter, report: MinifyReport | None) -> None:
    if report is None:
        return
    reporter.summary(
        f"build: minified {report.minified_files}/{report.total_files} HTML files, "
        f"{report.bytes_saved} bytes smaller"
    )
    if report.failed_files:
        reporter.summary(f"build: {report.failed_files} file(s) could not be minified, left unchanged:")
        for path, error in report.failures[:MINIFY_FAILURES_SHOWN]:
            reporter.summary(f"  {path}: {error}")
        if report.failed_files > MINIFY_FAILURES_SHOWN:
            reporter.summary(f"  ... and {report.failed_files - MINIFY_FAILURES_SHOWN} more")


@cli.command()
@click.option("--port", type=int, default=DEFAULT_PORT, show_default=True, help="Localhost port to bind.")
@click.pass_context
def serve(ctx: click.Context, port: int) -> None:
    """Serve the last built site from .sndocs/site/ on localhost.

    A plain static file server: no rebuild, no watch, no MkDocs. What it serves is
    exactly what the last `sndocs build` produced, search index included. Press
    Ctrl+C to stop.
    """
    reporter: Reporter = ctx.obj
    if not SITE_DIR.is_dir():
        reporter.error(
            "Serve failed",
            f"{SITE_DIR} does not exist. Run `sndocs build` first, or populate it manually.",
        )
        raise SystemExit(1)

    def _announce(server: ThreadingHTTPServer) -> None:
        bound_host, bound_port = server.server_address[:2]
        reporter.summary(
            f"serve: serving {SITE_DIR} at http://{bound_host}:{bound_port}/ (press Ctrl+C to stop)"
        )

    try:
        serve_site(SITE_DIR, port=port, on_ready=_announce)
    except OSError as exc:
        reporter.error(
            "Serve failed",
            f"could not bind localhost:{port}: {exc}. Try another --port or free the "
            "one in use.",
        )
        reporter.print_exception(exc)
        raise SystemExit(1) from exc
    except Exception as exc:
        reporter.error("Serve failed", f"the static server stopped unexpectedly: {exc}")
        reporter.print_exception(exc)
        raise SystemExit(1) from exc
    reporter.summary("serve: stopped")


@cli.command(name="all")
@minify_options
@click.pass_context
def run_all(ctx: click.Context, minify: bool, minify_workers: int | None) -> None:
    """Run fetch, normalize, and build in sequence.

    A convenience wrapper for the full pipeline: from a clean checkout this takes
    you to a browsable local site in `.sndocs/site/` (ready for `sndocs serve`) in
    one command. Every run is a full rebuild — fetch resyncs the clone to the
    remote, normalize rewrites `.sndocs/normalized/` from scratch, and build
    re-renders `.sndocs/site/` from scratch, with no incremental/change-detection
    logic. If any step fails the run stops there with a clear error.

    `--minify` / `--minify-workers` are forwarded to the build step.
    """
    reporter: Reporter = ctx.obj
    steps: list[tuple[str, Callable[[], None]]] = [
        ("fetch", lambda: ctx.invoke(fetch)),
        ("normalize", lambda: ctx.invoke(normalize)),
        ("build", lambda: ctx.invoke(build, minify=minify, minify_workers=minify_workers)),
    ]

    # A failing step raises SystemExit (its own styled error already rendered by
    # the child command, issues #48–#50); that propagates straight out here,
    # stopping the pipeline before the next step and before the sign-off lines.
    timings: list[tuple[str, float]] = []
    run_started = time.monotonic()
    for position, (label, run_step) in enumerate(steps, start=1):
        reporter.step(f"[{position}/{len(steps)}] {label}")
        step_started = time.monotonic()
        run_step()
        timings.append((label, time.monotonic() - step_started))

    reporter.summary(f"all: fetch + normalize + build complete; {SITE_DIR} ready for `sndocs serve`")
    breakdown = " · ".join(f"{name} {_format_duration(seconds)}" for name, seconds in timings)
    reporter.summary(
        f"all: completed in {_format_duration(time.monotonic() - run_started)} ({breakdown})"
    )


def _format_duration(seconds: float) -> str:
    """Render an elapsed span for the `all` timing breakdown: ``38s`` under a
    minute, ``1m02s`` / ``4m12s`` above one — seconds zero-padded once minutes
    are shown."""
    minutes, secs = divmod(round(seconds), 60)
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


if __name__ == "__main__":
    cli()
