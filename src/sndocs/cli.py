import subprocess
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path

import click

from sndocs import __version__
from sndocs.build import PagefindIndexingFailed, build_site
from sndocs.fetch import fetch_repo
from sndocs.minify import MinifyReport
from sndocs.normalize import NormalizationFailed, normalize_corpus
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


@cli.command()
def fetch() -> None:
    """Clone or update the australia branch of ServiceNowDocs into .sndocs/repo/."""
    fetch_repo(REPO_DIR)
    click.echo(f"fetch: synced to {REPO_DIR}")


@cli.command()
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=None,
    help="Parallel workers (default: available CPU count).",
)
def normalize(workers: int | None) -> None:
    """Normalize .sndocs/repo/ into .sndocs/normalized/."""
    if not REPO_DIR.is_dir():
        raise click.ClickException(f"{REPO_DIR} does not exist. Run `sndocs fetch` first, or populate it manually.")
    try:
        report = normalize_corpus(REPO_DIR, NORMALIZED_DIR, workers=workers)
    except NormalizationFailed as exc:
        raise click.ClickException(str(exc)) from exc
    result = report["result"]
    click.echo(
        f"normalize: {result['succeeded']}/{result['total_files']} files normalized "
        f"into {NORMALIZED_DIR} ({result['changed_files']} changed)"
    )


@cli.command()
@minify_options
def build(minify: bool, minify_workers: int | None) -> None:
    """Build the MkDocs site from .sndocs/normalized/ into .sndocs/site/."""
    if minify_workers is not None and not minify:
        raise click.UsageError("--minify-workers has no effect without --minify.")
    if not NORMALIZED_DIR.is_dir():
        raise click.ClickException(
            f"{NORMALIZED_DIR} does not exist. Run `sndocs normalize` first, or populate it manually."
        )
    try:
        report = build_site(
            NORMALIZED_DIR, SITE_DIR, MKDOCS_CONFIG, minify=minify, minify_workers=minify_workers
        )
    except PagefindIndexingFailed as exc:
        raise click.ClickException(f"Pagefind indexing failed: {exc}") from exc
    click.echo(f"build: rendered {NORMALIZED_DIR} into {SITE_DIR}, indexed with Pagefind")
    _report_minify(report)


def _report_minify(report: MinifyReport | None) -> None:
    if report is None:
        return
    click.echo(
        f"build: minified {report.minified_files}/{report.total_files} HTML files, "
        f"{report.bytes_saved} bytes smaller"
    )
    if report.failed_files:
        click.echo(f"build: {report.failed_files} file(s) could not be minified, left unchanged:")
        for path, error in report.failures[:MINIFY_FAILURES_SHOWN]:
            click.echo(f"  {path}: {error}")
        if report.failed_files > MINIFY_FAILURES_SHOWN:
            click.echo(f"  ... and {report.failed_files - MINIFY_FAILURES_SHOWN} more")


@cli.command()
@click.option("--port", type=int, default=DEFAULT_PORT, show_default=True, help="Localhost port to bind.")
def serve(port: int) -> None:
    """Serve the last built site from .sndocs/site/ on localhost.

    A plain static file server: no rebuild, no watch, no MkDocs. What it serves is
    exactly what the last `sndocs build` produced, search index included. Press
    Ctrl+C to stop.
    """
    if not SITE_DIR.is_dir():
        raise click.ClickException(
            f"{SITE_DIR} does not exist. Run `sndocs build` first, or populate it manually."
        )

    def _announce(server: ThreadingHTTPServer) -> None:
        bound_host, bound_port = server.server_address[:2]
        click.echo(f"serve: serving {SITE_DIR} at http://{bound_host}:{bound_port}/ (press Ctrl+C to stop)")

    try:
        serve_site(SITE_DIR, port=port, on_ready=_announce)
    except OSError as exc:
        raise click.ClickException(f"could not bind localhost:{port}: {exc}") from exc
    click.echo("serve: stopped")


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
    try:
        ctx.invoke(fetch)
        ctx.invoke(normalize)
        ctx.invoke(build, minify=minify, minify_workers=minify_workers)
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"pipeline step failed: {exc}") from exc
    click.echo(f"all: fetch + normalize + build complete; {SITE_DIR} ready for `sndocs serve`")


if __name__ == "__main__":
    cli()
