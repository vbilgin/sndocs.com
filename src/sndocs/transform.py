from __future__ import annotations

import html
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

import yaml

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
OMITTED_IMAGE_RE = re.compile(r'\\?\[Omitted image\s+["“]([^"”]+)["”]\\?\](?:\s*Alt text:\s*([^\n]+))?')

KEPT_FRONTMATTER = {
    "title", "description", "locale", "canonical_url", "release", "topic_type",
    "last_updated", "reading_time_minutes", "keywords", "breadcrumb", "product_area",
}


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a mapping")
    return {key: value for key, value in metadata.items() if key in KEPT_FRONTMATTER}, text[match.end():]


def pretty_url(family: str, markdown_path: str, fragment: str = "") -> str:
    path = PurePosixPath(unquote(markdown_path))
    if path.name == "index.md":
        rendered = path.parent.as_posix().rstrip("/") + "/"
    else:
        rendered = path.with_suffix("").as_posix().rstrip("/") + "/"
    return f"/{family}/{rendered}{fragment}"


def rewrite_links(
    body: str, current_family: str, current_path: PurePosixPath, families: set[str], repository: str
) -> str:
    raw_link_re = re.compile(
        rf"https://raw\.githubusercontent\.com/{re.escape(repository)}/([^/]+)/markdown/([^\s)]+\.md)(#[^\s)]*)?"
    )
    def replace(match: re.Match) -> str:
        family, target, fragment = match.group(1), unquote(match.group(2)), match.group(3) or ""
        if family not in families:
            return match.group(0)
        if family != current_family:
            return pretty_url(family, target, fragment)
        relative = os.path.relpath(target, start=current_path.parent.as_posix())
        return PurePosixPath(relative).as_posix() + fragment
    return raw_link_re.sub(replace, body)


def enrich_body(body: str, metadata: dict, family: str, source_url: str) -> str:
    def image_notice(match: re.Match) -> str:
        filename = html.escape(match.group(1))
        alt = html.escape((match.group(2) or "No alternative text supplied").strip())
        return f'\n<div class="omitted-image" role="note"><strong>Image omitted:</strong> {filename}<br><span>{alt}</span></div>\n'

    body = OMITTED_IMAGE_RE.sub(image_notice, body)
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
) -> str:
    metadata, body = split_frontmatter(text)
    if not body.strip():
        title = metadata.get("title") or relative_path.stem.replace("-", " ").title()
        body = f"# {title}\n\n!!! warning \"Source content unavailable\"\n    The upstream file is currently empty. This placeholder preserves incoming links.\n"
    body = rewrite_links(body, family, relative_path, families, repository)
    body = enrich_body(body, metadata, family, source_url)
    return "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip() + "\n---\n\n" + body


def transform_tree(source_markdown: Path, docs_dir: Path, family: str, families: set[str], repository: str) -> None:
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
        target.write_text(transform_document(text, family, relative, families, source_url, repository), encoding="utf-8")
