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
from sndocs.serve import DEFAULT_PORT, serve_site

REPO_DIR = Path(".sndocs") / "repo"
NORMALIZED_DIR = Path(".sndocs") / "normalized"
SITE_DIR = Path(".sndocs") / "site"
MKDOCS_CONFIG = Path("mkdocs.yml")

# Cap on per-file minify errors listed individually in the build output.
MINIFY_FAILURES_SHOWN = 10


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


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="sndocs")
def cli() -> None:
    """Fetch, normalize, and build a local ServiceNowDocs site."""


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
