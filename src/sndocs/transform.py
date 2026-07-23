from __future__ import annotations

import html
import os
import posixpath
import re
import shutil
import textwrap
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

import yaml
from markdown import markdown

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
    r'\s*(?:Alt text:\s*)?(?P<description>.*?)\]\((?P<target>[^\s)]+)\)\s*$',
    re.IGNORECASE | re.DOTALL,
)
NAV_CARD_SPLIT_RE = re.compile(
    r"^\s*\[(?P<title>[^]\n]+)]\((?P<target>[^\s)]+)\)\s*"
    r"\[\\?\[Omitted image\s+[\"“][^\"”]+[\"”]\\?]\s*Alt text:\s*]\((?P=target)\)\s*"
    r"\[(?P<description>[^]\n]+)]\((?P=target)\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
NAV_CARD_STATIC_RE = re.compile(
    r'^\s*(?P<title>.*?)\\?\[Omitted image\s+[\"“][^\"”]+[\"”]\\?]'
    r"\s*(?:Alt text:\s*)?(?P<description>.*?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
HTML_ID_RE = re.compile(r'\bid\s*=\s*(["\'])(?P<value>.*?)\1', re.IGNORECASE | re.DOTALL)
TABLE_RE = re.compile(r"<table\b(?P<attrs>[^>]*)>(?P<body>.*?)</table\s*>", re.IGNORECASE | re.DOTALL)
TABLE_CELL_RE = re.compile(
    r"<(?P<tag>td|th)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
INLINE_MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[(?P<label>[^]\n]{1,500})]\((?P<target>[^()\s\n]{1,1000})\)"
)


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
            card = NAV_CARD_SPLIT_RE.fullmatch(raw_cell) or NAV_CARD_LINK_RE.fullmatch(raw_cell)
            if card is None:
                links = list(INLINE_MARKDOWN_LINK_RE.finditer(raw_cell))
                if "Omitted image" in raw_cell and links:
                    first_link = links[0]
                    description_match = re.search(
                        r"Alt text:\s*(?P<description>.*?)(?:]\([^)]*\))?\s*$",
                        raw_cell,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if description_match is not None:
                        target = html.escape(
                            _navigation_card_url(first_link.group("target"), current_path),
                            quote=True,
                        )
                        cards.append(
                            f'<a class="nav-card__item" href="{target}">'
                            f'<strong class="nav-card__title">{html.escape(first_link.group("label").strip())}</strong>'
                            f'<span class="nav-card__description">{html.escape(description_match.group("description").strip())}</span></a>'
                        )
                        continue
                static_card = NAV_CARD_STATIC_RE.fullmatch(raw_cell)
                if static_card is None:
                    return match.group(0)
                cards.append(
                    '<div class="nav-card__item">'
                    f'<strong class="nav-card__title">{html.escape(static_card.group("title").strip())}</strong>'
                    f'<span class="nav-card__description">{html.escape(static_card.group("description").strip())}</span>'
                    "</div>"
                )
                continue
            raw_title = card.group("title").strip()
            embedded_title = INLINE_MARKDOWN_LINK_RE.search(raw_title)
            if embedded_title is not None:
                raw_title = embedded_title.group("label").lstrip("[").strip()
            raw_description = card.group("description").strip()
            duplicate_prefix = re.compile(
                rf"^{re.escape(raw_title)}]\([^)]*\)\s*", re.IGNORECASE
            )
            raw_description = duplicate_prefix.sub("", raw_description)
            raw_description = INLINE_MARKDOWN_LINK_RE.sub(
                lambda link: link.group("label").strip(), raw_description
            )
            raw_description = re.sub(r"\[\s*]\([^)]*\)", "", raw_description)
            raw_description = raw_description.lstrip("[").strip()
            title = html.escape(raw_title)
            description = html.escape(raw_description)
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


def _table_link_url(
    target: str,
    current_path: PurePosixPath,
    resolver: FamilyLinkResolver | None,
) -> str:
    parsed = urlparse(html.unescape(target))
    if parsed.scheme or parsed.netloc or target.startswith(("/", "#")) or not parsed.path.endswith(".md"):
        return target
    source_target = PurePosixPath(
        posixpath.normpath(posixpath.join(current_path.parent.as_posix(), unquote(parsed.path)))
    )
    if resolver is not None:
        source_target = resolver.resolve(source_target, current_path)
    current_rendered = current_path.parent if current_path.name == "index.md" else current_path.with_suffix("")
    target_rendered = source_target.parent if source_target.name == "index.md" else source_target.with_suffix("")
    relative = posixpath.relpath(target_rendered.as_posix(), start=current_rendered.as_posix())
    rendered = "./" if relative == "." else relative.rstrip("/") + "/"
    return rendered + (f"?{parsed.query}" if parsed.query else "") + (f"#{parsed.fragment}" if parsed.fragment else "")


def transform_table_markdown(
    body: str,
    current_path: PurePosixPath,
    resolver: FamilyLinkResolver | None = None,
) -> str:
    """Render inline Markdown found inside ordinary upstream HTML table cells."""

    protected: list[str] = []

    def protect_navigation_card(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00SN_NAV_CARD_{len(protected) - 1}\x00"

    body = NAV_CARD_TABLE_RE.sub(protect_navigation_card, body)

    table_depth = 0
    code_depth = 0
    fence_open = False
    parts = re.split(r"(<[^>]+>)", body)
    for index, part in enumerate(parts):
        if not part.startswith("<"):
            if table_depth and not code_depth:
                def render_link(link_match: re.Match) -> str:
                    label = re.sub(r"\\([()[\]_*])", r"\1", link_match.group("label"))
                    target = _table_link_url(link_match.group("target"), current_path, resolver)
                    return (
                        f'<a href="{html.escape(target, quote=True)}">'
                        f"{html.escape(label)}</a>"
                    )

                text_parts = re.split(r"(```)", part)
                for text_index, text_part in enumerate(text_parts):
                    if text_part == "```":
                        fence_open = not fence_open
                    elif not fence_open:
                        text_parts[text_index] = INLINE_MARKDOWN_LINK_RE.sub(
                            render_link, text_part
                        )
                parts[index] = "".join(text_parts)
            continue
        tag = re.match(r"</?\s*([a-zA-Z0-9]+)", part)
        if tag is None:
            continue
        name = tag.group(1).casefold()
        closing = bool(re.match(r"</", part))
        if name == "table":
            table_depth += -1 if closing else 1
        elif name in {"pre", "code"}:
            code_depth += -1 if closing else 1
    body = "".join(parts)

    def replace_cell(cell_match: re.Match) -> str:
        cell_body = cell_match.group("body")
        if not re.search(r"(?<![\\!])(?:\[[^\n]+]\([^)]+\)|\*\*[^*\n]+\*\*|__[^_\n]+__)", cell_body):
            return cell_match.group(0)

        def rewrite_target(link_match: re.Match) -> str:
            label = link_match.group("label")
            target = _table_link_url(link_match.group("target"), current_path, resolver)
            return f"[{label}]({target})"

        rewritten = INLINE_MARKDOWN_LINK_RE.sub(rewrite_target, cell_body)
        rewritten = textwrap.dedent(rewritten).strip()
        rewritten = re.sub(r"(?m)^(?: {4}|\t)(?=-\s{3})", "", rewritten)
        rendered = markdown(rewritten, extensions=["pymdownx.superfences"]).strip()
        if rendered.startswith("<p>") and rendered.endswith("</p>") and rendered.count("<p>") == 1:
            rendered = rendered[3:-4]
        return (
            f'<{cell_match.group("tag")}{cell_match.group("attrs")}>'
            f"{rendered}</{cell_match.group('tag')}>"
        )

    body = TABLE_CELL_RE.sub(replace_cell, body)
    body = re.sub(r"</table\s*>(?!\s*\n\s*\n)", "</table>\n\n", body, flags=re.IGNORECASE)
    for index, table in enumerate(protected):
        body = body.replace(f"\x00SN_NAV_CARD_{index}\x00", table)
    return body


def normalize_fenced_code_boundaries(body: str) -> str:
    """Put standalone fenced-code markers on Markdown block boundaries."""
    body = re.sub(r"(?m)(?<=\S)[ \t]*(```[^\n]*)$", r"\n\n\1", body)
    result: list[str] = []
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```") and result and result[-1].strip():
            result.append("\n")
        result.append(line)
    return "".join(result)


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
    if isinstance(metadata.get("title"), str):
        metadata["title"] = re.sub(r"\\([()[\]_*])", r"\1", metadata["title"])
    if not body.strip():
        title = metadata.get("title") or relative_path.stem.replace("-", " ").title()
        body = f"# {title}\n\n!!! warning \"Source content unavailable\"\n    The upstream file is currently empty. This placeholder preserves incoming links.\n"
    body = rewrite_links(body, family, relative_path, families, repository, resolver)
    body = transform_navigation_cards(body, relative_path)
    body = rewrite_missing_images(body, relative_path, source_files, resolver)
    body = transform_table_markdown(body, relative_path, resolver)
    body = normalize_fenced_code_boundaries(body)
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
