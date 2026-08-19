"""Rewrite ServiceNowDocs raw-GitHub `.md` links into relative links.

ServiceNowDocs source Markdown links to other pages in the corpus using the
raw-GitHub URL for the `australia` branch, e.g.
`https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/<category>/<page>.md`.
MkDocs can't resolve that as an in-site link, so this module rewrites only
links matching that exact pattern where the target file exists in the
corpus, into a relative `.md` link that MkDocs resolves to the built page.
Everything else (external links, GitHub links to files not in the corpus,
non-matching link shapes) is left untouched.
"""

from __future__ import annotations

import posixpath
import re
from collections import Counter

RAW_LINK_RE = re.compile(
    r"https://raw\.githubusercontent\.com/ServiceNow/ServiceNowDocs/australia/"
    r"(?P<path>[^\s)\]<>\"'#]+\.md)(?P<fragment>#[^\s)\]<>\"']*)?"
)


def rewrite_links(text: str, known_paths: frozenset[str], source_path: str) -> tuple[str, Counter[str]]:
    """Rewrite raw-GitHub `.md` links in `text` that target a file in `known_paths`
    (corpus-relative, forward-slash paths) into a relative link from `source_path`
    (the corpus-relative path of the file `text` belongs to). Links to targets not
    in `known_paths`, and non-matching URLs, are returned unchanged."""
    stats: Counter[str] = Counter()
    source_dir = posixpath.dirname(source_path)

    def replace(match: re.Match[str]) -> str:
        path = match.group("path")
        if path not in known_paths:
            return match.group(0)
        fragment = match.group("fragment") or ""
        relative = posixpath.relpath(path, source_dir) if source_dir else path
        stats["raw_github_links_rewritten"] += 1
        return relative + fragment

    return RAW_LINK_RE.sub(replace, text), stats
