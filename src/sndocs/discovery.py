from __future__ import annotations

import re
from .models import Discovery, Publication, Settings
from .source import RemoteSource, SourceRepository

FAMILY_RE = re.compile(r'^\s*-\s+"([^"]+)"\s*:\s*"([^"]+)"', re.MULTILINE)
PUBLICATION_RE = re.compile(
    r"^- \[([^]]+)]\((https://raw\.githubusercontent\.com/[^)]+/markdown/([^/]+)/index\.md)\)",
    re.MULTILINE,
)


def parse_llms(text: str, allowlist: tuple[str, ...] = ()) -> Discovery:
    mapped = [branch for family, branch in FAMILY_RE.findall(text) if family == branch]
    if not mapped:
        raise ValueError("llms.txt did not contain a family-to-branch mapping")
    families = [family for family in mapped if not allowlist or family in allowlist]
    if not families:
        raise ValueError("family allowlist excluded every discovered family")
    publications: list[Publication] = []
    seen: set[str] = set()
    for name, url, slug in PUBLICATION_RE.findall(text):
        if slug not in seen:
            publications.append(Publication(name=name.strip(), slug=slug, index_url=url))
            seen.add(slug)
    if not publications:
        raise ValueError("llms.txt did not contain publication index links")
    return Discovery(families=families, latest=families[0], publications=publications)


def discover(settings: Settings, source: SourceRepository | None = None) -> Discovery:
    source = source or RemoteSource()
    result = parse_llms(source.read_llms(settings), settings.family_allowlist)
    result.shas = source.resolve_shas(settings, result.families)
    return result
