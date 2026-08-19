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

import subprocess
import sys
from pathlib import Path

import yaml
from mkdocs.commands.build import build as mkdocs_build
from mkdocs.config import load_config

NavEntry = dict[str, "str | list[NavEntry]"]


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


def run_pagefind(site_dir: Path) -> None:
    """Indexes the rendered `site_dir` in place with Pagefind, invoked as a subprocess
    (not the `pagefind.service`/`pagefind.index` Python API) against the final HTML
    output. Also emits the `pagefind-ui` widget assets into `site_dir/pagefind/`,
    which the `overrides/main.html` theme override wires up as the site's search box."""
    result = subprocess.run(
        [sys.executable, "-m", "pagefind", "--site", str(site_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PagefindIndexingFailed(result.stderr.strip() or result.stdout.strip())


def build_site(docs_dir: Path, site_dir: Path, config_file: Path) -> None:
    """Render `docs_dir` into `site_dir` with MkDocs + Material, using `config_file`
    for theme/site settings and a freshly computed nav, then index the rendered site
    with Pagefind. The MkDocs render is offline: no network access is made. Pagefind
    indexing runs a locally-installed subprocess and likewise makes no network calls."""
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"{docs_dir} does not exist.")
    config = load_config(str(config_file), nav=build_nav(docs_dir), site_dir=str(site_dir))
    mkdocs_build(config)
    run_pagefind(site_dir)
