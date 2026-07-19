from __future__ import annotations

import html
import os
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

import yaml

from .links import FamilyLinkResolver
from .metadata import split_frontmatter

OMITTED_IMAGE_RE = re.compile(r'\\?\[Omitted image\s+["“]([^"”]+)["”]\\?\](?:\s*Alt text:\s*([^\n]+))?')
MARKDOWN_IMAGE_RE = re.compile(
    r'!\[([^]]*)\]\(([^\s)]+)(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\)))?\)'
)
RAW_HTML_CONTAINER_RE = re.compile(
    r"<(table|div|details|figure|section|article|aside|nav|header|footer)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
NAV_CARD_TABLE_RE = re.compile(
    r'<table\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bnav-card\b[^"\']*["\'])(?P<attrs>[^>]*)>'
    r"(?P<body>.*?)</table\s*>",
    re.IGNORECASE | re.DOTALL,
)
NAV_CARD_CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td\s*>", re.IGNORECASE | re.DOTALL)
NAV_CARD_LINK_RE = re.compile(
    r'^\s*\[(?P<title>.*?)\\?\[Omitted image\s+["“](?P<image>[^"”]+)["”]\\?\]'
    r'\s*Alt text:\s*(?P<description>.*?)\]\((?P<target>[^\s)]+)\)\s*$',
    re.IGNORECASE | re.DOTALL,
)
HTML_ID_RE = re.compile(r'\bid\s*=\s*(["\'])(?P<value>.*?)\1', re.IGNORECASE | re.DOTALL)


def _image_notice(filename: str, alt: str) -> str:
    escaped_filename = html.escape(filename)
    escaped_alt = html.escape(alt.strip() or "No alternative text supplied")
    return (
        '\n<div class="omitted-image" role="note"><strong>Image omitted:</strong> '
        f'{escaped_filename}<br><span>{escaped_alt}</span></div>\n'
    )


def pretty_url(family: str, markdown_path: str, fragment: str = "") -> str:
    path = PurePosixPath(unquote(markdown_path))
    if path.name == "index.md":
        rendered = path.parent.as_posix().rstrip("/") + "/"
    else:
        rendered = path.with_suffix("").as_posix().rstrip("/") + "/"
    return f"/{family}/{rendered}{fragment}"


def rewrite_links(
    body: str,
    current_family: str,
    current_path: PurePosixPath,
    families: set[str],
    repository: str,
    resolver: FamilyLinkResolver | None = None,
) -> str:
    raw_link_re = re.compile(
        rf"https://raw\.githubusercontent\.com/{re.escape(repository)}/([^/]+)/markdown/([^\s)\]]+\.md)(#[^\s)]*)?"
    )
    def replace(match: re.Match) -> str:
        family, target, fragment = match.group(1), unquote(match.group(2)), match.group(3) or ""
        if family not in families:
            return match.group(0)
        if family != current_family:
            return pretty_url(family, target, fragment)
        if resolver:
            target = str(resolver.resolve(target, current_path))
        relative = os.path.relpath(target, start=current_path.parent.as_posix())
        return PurePosixPath(relative).as_posix() + fragment
    return raw_link_re.sub(replace, body)


def _navigation_card_url(target: str, current_path: PurePosixPath) -> str:
    parsed = urlparse(html.unescape(target))
    if parsed.scheme or parsed.netloc or target.startswith(("/", "#")) or not parsed.path.endswith(".md"):
        return target
    source_target = PurePosixPath(
        posixpath.normpath(posixpath.join(current_path.parent.as_posix(), unquote(parsed.path)))
    )
    current_rendered = current_path.parent if current_path.name == "index.md" else current_path.with_suffix("")
    target_rendered = source_target.parent if source_target.name == "index.md" else source_target.with_suffix("")
    relative = posixpath.relpath(target_rendered.as_posix(), start=current_rendered.as_posix())
    rendered = "./" if relative == "." else relative.rstrip("/") + "/"
    return rendered + (f"?{parsed.query}" if parsed.query else "") + (f"#{parsed.fragment}" if parsed.fragment else "")


def transform_navigation_cards(body: str, current_path: PurePosixPath) -> str:
    """Convert recognized upstream navigation tables into semantic linked cards."""

    def replace_table(match: re.Match) -> str:
        cards: list[str] = []
        for raw_cell in NAV_CARD_CELL_RE.findall(match.group("body")):
            visible_cell = html.unescape(re.sub(r"<[^>]+>", "", raw_cell)).strip()
            if not visible_cell:
                continue
            card = NAV_CARD_LINK_RE.fullmatch(raw_cell)
            if card is None:
                return match.group(0)
            title = html.escape(card.group("title").strip())
            description = html.escape(card.group("description").strip())
            target = html.escape(
                _navigation_card_url(card.group("target"), current_path), quote=True
            )
            cards.append(
                f'<a class="nav-card__item" href="{target}">'
                f'<strong class="nav-card__title">{title}</strong>'
                f'<span class="nav-card__description">{description}</span></a>'
            )
        if not cards:
            return match.group(0)
        id_match = HTML_ID_RE.search(match.group("attrs"))
        identifier = (
            f' id="{html.escape(id_match.group("value"), quote=True)}"' if id_match else ""
        )
        return f'\n<div class="nav-card-grid"{identifier}>\n' + "\n".join(cards) + "\n</div>\n"

    return NAV_CARD_TABLE_RE.sub(replace_table, body)


def rewrite_missing_images(
    body: str,
    current_path: PurePosixPath,
    source_files: set[PurePosixPath] | None,
    resolver: FamilyLinkResolver | None,
) -> str:
    if source_files is None:
        return body
    raw_html_spans = [match.span() for match in RAW_HTML_CONTAINER_RE.finditer(body)]

    def replace(match: re.Match) -> str:
        if any(start <= match.start() < end for start, end in raw_html_spans):
            return match.group(0)
        alt, raw_target = match.group(1), match.group(2)
        parsed = urlparse(raw_target)
        if parsed.scheme or parsed.netloc or raw_target.startswith(("/", "#")):
            return match.group(0)
        target_value = posixpath.normpath(
            posixpath.join(current_path.parent.as_posix(), unquote(parsed.path))
        )
        if target_value == ".." or target_value.startswith("../"):
            return match.group(0)
        target = PurePosixPath(target_value)
        if target in source_files:
            return match.group(0)
        if resolver is not None:
            resolver.record_omitted_image(current_path, target, alt)
        return _image_notice(target.name, alt)

    return MARKDOWN_IMAGE_RE.sub(replace, body)


def enrich_body(body: str, metadata: dict, family: str, source_url: str) -> str:
    def replace_omitted_image(match: re.Match) -> str:
        return _image_notice(
            match.group(1), match.group(2) or "No alternative text supplied"
        )

    body = OMITTED_IMAGE_RE.sub(replace_omitted_image, body)
    breadcrumb = metadata.get("breadcrumb")
    crumbs = " › ".join(str(item) for item in breadcrumb) if isinstance(breadcrumb, list) else ""
    canonical = metadata.get("canonical_url")
    links = [f'<a href="{html.escape(source_url)}">View source</a>']
    if canonical:
        links.insert(0, f'<a href="{html.escape(str(canonical))}">Official documentation</a>')
    details = [f"Release: {html.escape(family.title())}"]
    if metadata.get("last_updated"):
        details.append(f"Updated: {html.escape(str(metadata['last_updated']))}")
    header = '<div class="page-meta">'
    if crumbs:
        header += f'<div class="breadcrumbs">{html.escape(crumbs)}</div>'
    header += f'<div>{" · ".join(details)} · {" · ".join(links)}</div></div>\n\n'
    return header + body


def transform_document(
    text: str,
    family: str,
    relative_path: PurePosixPath,
    families: set[str],
    source_url: str,
    repository: str = "ServiceNow/ServiceNowDocs",
    resolver: FamilyLinkResolver | None = None,
    source_files: set[PurePosixPath] | None = None,
) -> str:
    metadata, body = split_frontmatter(text)
    if not body.strip():
        title = metadata.get("title") or relative_path.stem.replace("-", " ").title()
        body = f"# {title}\n\n!!! warning \"Source content unavailable\"\n    The upstream file is currently empty. This placeholder preserves incoming links.\n"
    body = rewrite_links(body, family, relative_path, families, repository, resolver)
    body = transform_navigation_cards(body, relative_path)
    body = rewrite_missing_images(body, relative_path, source_files, resolver)
    body = enrich_body(body, metadata, family, source_url)
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip() + "\n---\n\n" + body


def _write_missing_placeholders(docs_dir: Path, resolver: FamilyLinkResolver) -> None:
    for missing_path, referrers in resolver.missing.items():
        target = docs_dir / Path(missing_path.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        referring_list = "\n".join(
            f"- {kind}: `{path}`"
            for kind, path in sorted(referrers, key=lambda item: (item[0], str(item[1])))
        )
        title = missing_path.stem.replace("-", " ").title()
        content = f'''---
title: "[Unavailable] {title}"
description: The referenced document is not present in this upstream release.
release: {resolver.family}
---

# Upstream document unavailable

!!! warning "Missing from the upstream release"
    The source repository references `{missing_path}`, but that file is not present in the
    **{resolver.family.title()}** documentation branch. This generated placeholder preserves the link.

## Referenced by

{referring_list}
'''
        target.write_text(content, encoding="utf-8")


def write_missing_placeholders(docs_dir: Path, resolver: FamilyLinkResolver) -> None:
    _write_missing_placeholders(docs_dir, resolver)


def transform_tree(
    source_markdown: Path,
    docs_dir: Path,
    family: str,
    families: set[str],
    repository: str,
    resolver: FamilyLinkResolver | None = None,
    *,
    finalize: bool = True,
) -> dict:
    resolver = resolver or FamilyLinkResolver(source_markdown, family)
    source_files = {
        PurePosixPath(path.relative_to(source_markdown).as_posix())
        for path in source_markdown.rglob("*")
        if path.is_file()
    }
    destinations: dict[str, PurePosixPath] = {}
    for source in source_markdown.rglob("*.md"):
        relative = PurePosixPath(source.relative_to(source_markdown).as_posix())
        collision_key = relative.as_posix().casefold()
        if collision_key in destinations:
            raise ValueError(f"case-insensitive output collision: {destinations[collision_key]} and {relative}")
        destinations[collision_key] = relative
        target = docs_dir / Path(relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        source_url = f"https://github.com/{repository}/blob/{family}/markdown/{relative.as_posix()}"
        text = source.read_text(encoding="utf-8", errors="replace")
        target.write_text(
            transform_document(
                text,
                family,
                relative,
                families,
                source_url,
                repository,
                resolver,
                source_files,
            ),
            encoding="utf-8",
        )
    for relative in sorted(source_files, key=str):
        if relative.suffix.casefold() == ".md":
            continue
        target = docs_dir / Path(relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_markdown / Path(relative.as_posix()), target)
    if finalize:
        _write_missing_placeholders(docs_dir, resolver)
    return resolver.report()
