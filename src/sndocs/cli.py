from pathlib import Path

import click

from sndocs.fetch import fetch_repo
from sndocs.normalize import NormalizationFailed, normalize_corpus

REPO_DIR = Path(".sndocs") / "repo"
NORMALIZED_DIR = Path(".sndocs") / "normalized"


@click.group()
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
def build() -> None:
    """Build the MkDocs site and run Pagefind indexing into .sndocs/site/."""
    click.echo("build: not yet implemented")


@cli.command()
def serve() -> None:
    """Serve the last built site from .sndocs/site/."""
    click.echo("serve: not yet implemented")


@cli.command(name="all")
def run_all() -> None:
    """Run fetch, normalize, and build in sequence."""
    click.echo("all: not yet implemented")


if __name__ == "__main__":
    cli()
