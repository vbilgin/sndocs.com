from __future__ import annotations

import re
from pathlib import Path

import yaml

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

KEPT_FRONTMATTER = {
    "title", "description", "locale", "canonical_url", "release", "topic_type",
    "last_updated", "reading_time_minutes", "keywords", "breadcrumb", "product_area",
}
SCALAR_FRONTMATTER = {
    "title", "description", "locale", "canonical_url", "release", "topic_type", "product_area",
}


def _parse_frontmatter_fallback(frontmatter: str) -> dict:
    """Recover simple top-level fields from invalid upstream YAML."""
    metadata: dict = {}
    for line in frontmatter.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
        if not match:
            continue
        key, raw_value = match.group(1), (match.group(2) or "").strip()
        if key not in KEPT_FRONTMATTER:
            continue
        if key in SCALAR_FRONTMATTER:
            if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "\"'":
                try:
                    metadata[key] = yaml.safe_load(raw_value)
                    continue
                except yaml.YAMLError:
                    pass
            metadata[key] = raw_value
            continue
        try:
            metadata[key] = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            metadata[key] = raw_value
    return metadata


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = _parse_frontmatter_fallback(match.group(1))
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a mapping")
    return {key: value for key, value in metadata.items() if key in KEPT_FRONTMATTER}, text[match.end():]


def read_frontmatter(path: Path) -> dict:
    """Read and parse only a document's leading frontmatter block."""
    lines: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        if handle.readline().strip() != "---":
            return {}
        lines.append("---\n")
        for line in handle:
            lines.append(line)
            if line.strip() == "---":
                break
        else:
            return {}
    metadata, _ = split_frontmatter("".join(lines))
    return metadata
