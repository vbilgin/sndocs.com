from pathlib import PurePosixPath

import pytest

from sndocs.transform import split_frontmatter, transform_document, transform_tree


def test_transform_keeps_metadata_rewrites_links_and_enriches_images():
    text = '''---
title: Example
canonical_url: https://www.servicenow.com/docs/example
secret: discard-me
breadcrumb: [Home, Example]
---
# Example

[Local](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/other.md)
[Old](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/zurich/markdown/pub/old.md#part)
\\[Omitted image "screen.png"\\] Alt text: useful screenshot
'''
    result = transform_document(
        text, "australia", PurePosixPath("pub/current.md"), {"australia", "zurich"}, "https://github.com/source"
    )
    metadata, body = split_frontmatter(result)
    assert metadata["title"] == "Example"
    assert "secret" not in metadata
    assert "other.md" in body
    assert "/zurich/pub/old/#part" in body
    assert "omitted-image" in body and "useful screenshot" in body
    assert "Official documentation" in body and "View source" in body


def test_empty_document_gets_diagnostic_placeholder():
    result = transform_document("---\ntitle: Empty\n---\n", "australia", PurePosixPath("pub/empty.md"), {"australia"}, "source")
    assert "Source content unavailable" in result


def test_malformed_unquoted_colon_in_frontmatter_is_preserved():
    text = """---
title: Products required to enable ITOM AIOps functionality: ITOM AIOps and Now Assist for ITOM
release: australia
keywords: [AIOps, ITOM]
---
# Requirements
"""
    metadata, body = split_frontmatter(text)
    assert metadata["title"] == "Products required to enable ITOM AIOps functionality: ITOM AIOps and Now Assist for ITOM"
    assert metadata["release"] == "australia"
    assert metadata["keywords"] == ["AIOps", "ITOM"]
    assert body == "# Requirements\n"


def test_unknown_family_link_is_preserved():
    url = "https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/unknown/markdown/pub/a.md"
    result = transform_document(url, "australia", PurePosixPath("pub/a.md"), {"australia"}, "source")
    assert url in result


def test_configured_upstream_repository_is_rewritten():
    url = "https://raw.githubusercontent.com/example/docs/australia/markdown/pub/b.md"
    result = transform_document(
        url, "australia", PurePosixPath("pub/a.md"), {"australia"}, "source", "example/docs"
    )
    assert url not in result and "b.md" in result


def test_case_insensitive_output_collision_is_rejected(tmp_path):
    source = tmp_path / "markdown" / "pub"
    source.mkdir(parents=True)
    (source / "Page.md").write_text("# One", encoding="utf-8")
    (source / "page.md").write_text("# Two", encoding="utf-8")
    if len(list(source.glob("*.md"))) < 2:
        pytest.skip("filesystem is case insensitive")
    with pytest.raises(ValueError, match="collision"):
        transform_tree(tmp_path / "markdown", tmp_path / "docs", "australia", {"australia"}, "owner/repo")
