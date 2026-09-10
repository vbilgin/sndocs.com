"""Build the MkDocs site from normalized Markdown, with an auto-generated nav.

MkDocs is driven entirely through its Python API (`mkdocs.commands.build`), so the
build never shells out and never touches the network: the corpus is already on disk
in `.sndocs/normalized/`, and Material's font loading is disabled in `mkdocs.yml`
(the only piece of Material that otherwise reaches out to a CDN at build time).

`nav:` is deliberately absent from `mkdocs.yml` — it's computed here on every build
by walking `docs_dir` and mirroring its directory structure. A directory holding
Markdown files of its own becomes a nav section (labelled from its `index.md`
front-matter `title`, or its directory name if there's no `index.md`); a directory
that holds only subdirectories is a pure pass-through and doesn't get its own nav
level, so a wrapper directory like the corpus's top-level `markdown/` doesn't turn
into a spurious top nav entry.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml
from mkdocs.commands.build import build as mkdocs_build
from mkdocs.config import load_config

from sndocs.minify import MinifyReport, html_files_in, minify_site

NavEntry = dict[str, "str | list[NavEntry]"]


class BuildObserver:
    """Progress and notification hooks for `build_site`, defaulting to silence.

    `sndocs.cli` passes a subclass backed by the shared `Reporter` (issue #49) so
    a `build` run announces each phase, shows a real bar for the minify pass, and
    hides MkDocs' `logging` chatter and Pagefind's stdout unless asked for them
    with `-v`. Direct callers and tests get this no-op base and see nothing.
    Keeping the protocol here means `sndocs.build` never imports `rich` or
    `sndocs.reporter` (ADR 0004)."""

    #: True when MkDocs' `logging` output and Pagefind's stdout should be routed
    #: back through `tool_line` rather than swallowed — i.e. the run is at `-v` or
    #: higher.
    surfaces_tool_output: bool = False

    @contextmanager
    def phase(self, label: str) -> Iterator[None]:
        """Wrap one opaque build phase (nav walk, MkDocs render, Pagefind index)
        in an indeterminate spinner with an elapsed timer."""
        yield

    @contextmanager
    def minify_progress(self, total: int) -> Iterator[Callable[..., None]]:
        """Wrap the minify pass in a determinate progress bar over `total`
        files. Yields a tick to call once per finished file."""
        yield lambda *_args, **_kwargs: None

    def tool_line(self, line: str) -> None:
        """Surface one line of MkDocs/Pagefind output. Only called when
        `surfaces_tool_output` is true — i.e. at `-v` and above, where INFO-level
        chatter is wanted too."""

    def tool_warning(self, line: str) -> None:
        """Surface one MkDocs WARNING/ERROR line as a grouped non-fatal warning.
        Called at every verbosity except `-v`+ (where `tool_line` already carries
        it): a broken internal link or a missing nav target must not vanish just
        because the INFO chatter around it is hidden."""


def _title_from_front_matter(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        return None
    try:
        data = yaml.safe_load("".join(lines[1:closing]))
    except yaml.YAMLError:
        return None
    title = data.get("title") if isinstance(data, dict) else None
    return title if isinstance(title, str) else None


def _humanize(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


def _page_label(path: Path) -> str:
    return _title_from_front_matter(path) or _humanize(path.stem)


def _relative(path: Path, docs_dir: Path) -> str:
    return path.relative_to(docs_dir).as_posix()


def _section_items(directory: Path, docs_dir: Path) -> list[NavEntry]:
    items: list[NavEntry] = []
    index = directory / "index.md"
    if index.is_file():
        items.append({_page_label(index): _relative(index, docs_dir)})
    files = sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".md" and p.name != "index.md"),
        key=lambda p: p.name,
    )
    for file_path in files:
        items.append({_page_label(file_path): _relative(file_path, docs_dir)})
    for subdir in sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name):
        items.extend(_nav_entry(subdir, docs_dir))
    return items


def _nav_entry(directory: Path, docs_dir: Path) -> list[NavEntry]:
    has_own_pages = any(p.is_file() and p.suffix.lower() == ".md" for p in directory.iterdir())
    items = _section_items(directory, docs_dir)
    if not has_own_pages:
        return items
    index = directory / "index.md"
    label = _page_label(index) if index.is_file() else _humanize(directory.name)
    return [{label: items}]


def build_nav(docs_dir: Path) -> list[NavEntry]:
    """Nav mirroring `docs_dir`'s directory tree, collapsing pass-through wrapper
    directories (ones with no Markdown files of their own) so only directories that
    actually hold pages become nav sections."""
    return _section_items(docs_dir, docs_dir)


class PagefindIndexingFailed(Exception):
    """Raised when the Pagefind subprocess exits non-zero; carries its stderr."""


def run_pagefind(site_dir: Path, *, on_output: Callable[[str], None] | None = None) -> None:
    """Indexes the rendered `site_dir` in place with Pagefind, invoked as a subprocess
    (not the `pagefind.service`/`pagefind.index` Python API) against the final HTML
    output. Also emits the `pagefind-ui` widget assets into `site_dir/pagefind/`,
    which the `overrides/main.html` theme override wires up as the site's search box.

    Pagefind's stdout is always captured; `on_output`, if given, is called once
    per non-blank line of it so a verbose run can surface the index summary
    (issue #49). Its stderr is still only surfaced on failure."""
    result = subprocess.run(
        [sys.executable, "-m", "pagefind", "--site", str(site_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PagefindIndexingFailed(result.stderr.strip() or result.stdout.strip())
    if on_output is not None:
        for line in result.stdout.splitlines():
            if line.strip():
                on_output(line)


@contextmanager
def _routed_mkdocs_logging(observer: BuildObserver) -> Iterator[None]:
    """Take over the ``mkdocs`` logger for the duration of the render so its
    output goes through `observer` instead of MkDocs' default stderr path.

    Nothing in this project configures that logger, so by default its records
    propagate to the root logger's last-resort handler (WARNING+ to stderr). We
    pin `propagate` off and attach one routing handler:

    * at `-v`+ (`surfaces_tool_output`): every record from INFO up goes to
      `tool_line`;
    * otherwise: INFO/DEBUG chatter is dropped, but WARNING/ERROR still reaches
      the user via `tool_warning` (grouped) — suppressing the noise must not
      also hide a broken-link or missing-file diagnostic.

    The logger is restored exactly as it was on exit."""
    logger = logging.getLogger("mkdocs")
    previous_level = logger.level
    previous_propagate = logger.propagate
    verbose = observer.surfaces_tool_output
    floor = logging.INFO if verbose else logging.WARNING

    class _Route(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            message = f"mkdocs: {record.getMessage()}"
            if verbose:
                observer.tool_line(message)
            else:
                observer.tool_warning(message)

    handler = _Route()
    handler.setLevel(floor)
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(floor)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def build_site(
    docs_dir: Path,
    site_dir: Path,
    config_file: Path,
    *,
    minify: bool = False,
    minify_workers: int | None = None,
    observer: BuildObserver | None = None,
) -> MinifyReport | None:
    """Render `docs_dir` into `site_dir` with MkDocs + Material, using `config_file`
    for theme/site settings and a freshly computed nav, then index the rendered site
    with Pagefind. The MkDocs render is offline: no network access is made. Pagefind
    indexing runs a locally-installed subprocess and likewise makes no network calls.

    With `minify=True`, every rendered `site_dir/**/*.html` file is run through
    `minify-html` between the MkDocs render and Pagefind indexing (the `pagefind/`
    directory does not exist yet, so the walk needs no exclusions), parallelised
    across `minify_workers` processes (default: CPU count). Returns the
    `MinifyReport` in that case, `None` otherwise.

    `observer` receives per-phase and per-file progress callbacks (issue #49);
    the default no-op `BuildObserver` renders nothing, so a direct caller sees
    the same silent behaviour as before."""
    observer = observer or BuildObserver()
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"{docs_dir} does not exist.")

    with observer.phase("nav walk"):
        nav = build_nav(docs_dir)
    config = load_config(str(config_file), nav=nav, site_dir=str(site_dir))

    with observer.phase("MkDocs render"), _routed_mkdocs_logging(observer):
        mkdocs_build(config)

    report = _minify_phase(site_dir, minify_workers, observer) if minify else None

    with observer.phase("Pagefind index"):
        run_pagefind(
            site_dir,
            on_output=observer.tool_line if observer.surfaces_tool_output else None,
        )
    return report


def _minify_phase(
    site_dir: Path, minify_workers: int | None, observer: BuildObserver
) -> MinifyReport:
    """Run the minify pass under `observer`'s determinate progress bar. The one
    walk of the rendered HTML here sizes the bar and is handed straight to
    `minify_site`, so the pass is not walked twice."""
    files = html_files_in(site_dir)
    with observer.minify_progress(len(files)) as tick:
        return minify_site(
            site_dir,
            workers=minify_workers,
            files=files,
            on_progress=lambda _result: tick(),
        )
