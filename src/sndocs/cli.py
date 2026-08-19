import click


@click.group()
def cli() -> None:
    """Fetch, normalize, and build a local ServiceNowDocs site."""


@cli.command()
def fetch() -> None:
    """Clone or update the australia branch of ServiceNowDocs into .sndocs/repo/."""
    click.echo("fetch: not yet implemented")


@cli.command()
def normalize() -> None:
    """Normalize the cloned corpus into .sndocs/normalized/."""
    click.echo("normalize: not yet implemented")


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
