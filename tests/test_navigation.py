from pathlib import PurePosixPath

import pytest

from sndocs.links import AmbiguousLinkError, FamilyLinkResolver
from sndocs.navigation import parse_index


def test_nested_index_becomes_mkdocs_navigation():
    text = '''
- [Parent](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/parent.md) -- summary
  - [Child](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/deep/child.md)
    - [Grandchild](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/deep/grand.md)
- [Leaf](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/leaf.md)
'''
    assert parse_index(text) == [
        {"Parent": ["pub/parent.md", {"Child": ["pub/deep/child.md", {"Grandchild": "pub/deep/grand.md"}]}]},
        {"Leaf": "pub/leaf.md"},
    ]


def test_navigation_uses_shared_resolution_and_tracks_duplicate_missing_references(tmp_path):
    markdown = tmp_path / "markdown"
    target = markdown / "pub" / "new" / "page.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Page", encoding="utf-8")
    resolver = FamilyLinkResolver(markdown, "australia")
    text = """
- [First](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/old/page.md)
- [Again](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/old/page.md)
- [Missing](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/missing.md)
"""

    nav = parse_index(text, resolver, PurePosixPath("pub/index.md"))

    assert nav[:2] == [
        {"First": "pub/new/page.md"},
        {"Again": "pub/new/page.md"},
    ]
    assert nav[2] == {"Missing": "pub/missing.md"}
    assert resolver.report()["counts"]["navigation_links"] == {
        "exact": 0,
        "repaired": 2,
        "missing": 1,
        "ambiguous": 0,
    }


def test_ambiguous_navigation_target_remains_fatal(tmp_path):
    markdown = tmp_path / "markdown"
    for path in (markdown / "one" / "page.md", markdown / "two" / "page.md"):
        path.parent.mkdir(parents=True)
        path.write_text("# Page", encoding="utf-8")
    resolver = FamilyLinkResolver(markdown, "australia")
    text = "- [Page](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/missing/page.md)"

    with pytest.raises(AmbiguousLinkError):
        parse_index(text, resolver, PurePosixPath("pub/index.md"))
