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

    assert nav == [
        {"First": "pub/new/page.md"},
        {"Missing": "pub/missing.md"},
    ]
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


def test_navigation_normalizes_markdown_escapes_and_preserves_literal_backslashes():
    text = r"""
- [API \(g\_aw\) \[client\] \*](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/api.md)
- [Windows C:\temp](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/windows.md)
"""

    assert parse_index(text) == [
        {"API (g_aw) [client] *": "pub/api.md"},
        {r"Windows C:\temp": "pub/windows.md"},
    ]


def test_navigation_deduplicates_exact_siblings_and_redundant_self_children():
    text = """
- [Parent](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/parent.md)
  - [Parent](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/parent.md)
  - [Parent details](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/parent.md)
  - [Child](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/child.md)
  - [Child](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/child.md)
- [Parent](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/parent.md)
- [Parent](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/other.md)
"""

    assert parse_index(text) == [
        {"Parent": ["pub/parent.md", {"Child": "pub/child.md"}]},
        {"Parent": "pub/other.md"},
    ]


def test_navigation_deduplicates_after_link_resolution(tmp_path):
    markdown = tmp_path / "markdown"
    target = markdown / "pub" / "moved" / "page.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Page", encoding="utf-8")
    resolver = FamilyLinkResolver(markdown, "australia")
    text = """
- [Page](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/old/page.md)
- [Page](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/moved/page.md)
"""

    assert parse_index(text, resolver, PurePosixPath("pub/index.md")) == [
        {"Page": "pub/moved/page.md"}
    ]


def test_navigation_keeps_only_first_occurrence_of_a_destination():
    text = """
- [First context](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/page.md)
- [Other section](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/other.md)
  - [Second context](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/page.md)
"""
    assert parse_index(text) == [
        {"First context": "pub/page.md"},
        {"Other section": "pub/other.md"},
    ]
