from pathlib import PurePosixPath

import pytest

from sndocs.links import FamilyLinkResolver
from sndocs.transform import (
    split_frontmatter,
    transform_document,
    transform_navigation_cards,
    normalize_fenced_code_boundaries,
    transform_table_markdown,
    transform_tree,
)


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


def test_markdown_escapes_are_removed_from_rendered_page_title_metadata():
    result = transform_document(
        "---\ntitle: API \\(g\\_aw\\) \\[client\\] \\*\n---\n# API",
        "australia",
        PurePosixPath("pub/api.md"),
        {"australia"},
        "source",
    )
    metadata, _ = split_frontmatter(result)
    assert metadata["title"] == "API (g_aw) [client] *"


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


def test_raw_url_used_as_link_label_and_destination_is_rewritten_twice():
    url = "https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/b.md"
    result = transform_document(
        f"[{url}]({url})",
        "australia",
        PurePosixPath("pub/a.md"),
        {"australia"},
        "source",
    )
    assert "raw.githubusercontent.com" not in result
    assert "[b.md](b.md)" in result


def test_case_insensitive_output_collision_is_rejected(tmp_path):
    source = tmp_path / "markdown" / "pub"
    source.mkdir(parents=True)
    (source / "Page.md").write_text("# One", encoding="utf-8")
    (source / "page.md").write_text("# Two", encoding="utf-8")
    if len(list(source.glob("*.md"))) < 2:
        pytest.skip("filesystem is case insensitive")
    with pytest.raises(ValueError, match="collision"):
        transform_tree(tmp_path / "markdown", tmp_path / "docs", "australia", {"australia"}, "owner/repo")


def test_missing_images_become_audited_notices_and_existing_assets_are_copied(tmp_path):
    source = tmp_path / "markdown" / "pub"
    source.mkdir(parents=True)
    (source / "page.md").write_text(
        "# Images\n\n"
        "![Missing <diagram>](image/missing.png)\n"
        "![Existing](image/existing.png)\n"
        "![External](https://example.com/image.png)\n"
        "<table><tr><td>\n![Raw HTML](image/raw-html.png)\n</td></tr></table>\n",
        encoding="utf-8",
    )
    image = source / "image" / "existing.png"
    image.parent.mkdir()
    image.write_bytes(b"png")

    docs = tmp_path / "docs"
    report = transform_tree(
        tmp_path / "markdown", docs, "australia", {"australia"}, "owner/repo"
    )

    rendered = (docs / "pub" / "page.md").read_text(encoding="utf-8")
    assert "Image omitted" in rendered and "Missing &lt;diagram&gt;" in rendered
    assert "![Existing](image/existing.png)" in rendered
    assert "https://example.com/image.png" in rendered
    assert "![Raw HTML](image/raw-html.png)" in rendered
    assert (docs / "pub" / "image" / "existing.png").read_bytes() == b"png"
    assert report["omitted_images"] == [
        {
            "source": "pub/page.md",
            "target": "pub/image/missing.png",
            "alt": "Missing <diagram>",
        }
    ]
    assert report["counts"]["omitted_images"] == {"occurrences": 1, "targets": 1}


@pytest.mark.parametrize("columns", [2, 3, 4])
def test_navigation_card_tables_become_adaptive_linked_cards(columns):
    cells = "".join(
        f'<td>\n\n[Card {index}\\[Omitted image "icon-{index}.svg"\\] '
        f'Alt text:Description {index}.](target-{index}.md#part)\n\n</td>'
        for index in range(columns)
    )
    text = f'<table id="card-table" class="nav-card presentation"><tbody><tr>{cells}</tr></tbody></table>'

    result = transform_document(
        text,
        "australia",
        PurePosixPath("pub/page.md"),
        {"australia"},
        "source",
    )

    assert result.count('class="nav-card__item"') == columns
    assert 'class="nav-card-grid" id="card-table"' in result
    assert 'href="../target-0/#part"' in result
    assert '<strong class="nav-card__title">Card 0</strong>' in result
    assert '<span class="nav-card__description">Description 0.</span>' in result
    assert "Omitted image" not in result


def test_navigation_cards_rewrite_family_links_and_drop_empty_cells():
    text = '''<table class="presentation nav-card"><tbody><tr><td>

[ServiceNow Vault\\[Omitted image "vault.svg"\\] Alt text:Protect sensitive data.](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/zurich/markdown/pub/vault.md)

</td><td> </td></tr></tbody></table>'''
    result = transform_document(
        text,
        "australia",
        PurePosixPath("pub/page.md"),
        {"australia", "zurich"},
        "source",
    )
    assert result.count('class="nav-card__item"') == 1
    assert 'href="/zurich/pub/vault/"' in result
    assert "[ServiceNow Vault" not in result


def test_navigation_card_without_alt_text_marker_is_still_recovered():
    text = '''<table class="nav-card"><tr><td>
[Developer \\[Omitted image "developer.png"\\] Build apps with code.](developer.md)
</td></tr></table>'''
    result = transform_navigation_cards(text, PurePosixPath("pub/index.md"))
    assert '<strong class="nav-card__title">Developer</strong>' in result
    assert '<span class="nav-card__description">Build apps with code.</span>' in result


def test_navigation_card_grid_can_include_non_linked_informational_card():
    text = '''<table class="nav-card"><tr><td>
[Linked \\[Omitted image "linked.png"\\] Alt text: Linked details.](linked.md)
</td><td>
Information \\[Omitted image "info.png"\\] Alt text: Informational details.
</td></tr></table>'''
    result = transform_navigation_cards(text, PurePosixPath("pub/index.md"))
    assert result.count('class="nav-card__item"') == 2
    assert result.count("<a ") == 1
    assert '<strong class="nav-card__title">Information</strong>' in result


def test_navigation_card_recovers_link_before_omitted_image():
    text = '''<table class="nav-card"><tr><td>
[Install](install.md)\\[Omitted image "install.png"\\] Alt text:Install the integration
</td></tr></table>'''
    result = transform_navigation_cards(text, PurePosixPath("pub/index.md"))
    assert 'href="install/"' in result
    assert '<strong class="nav-card__title">Install</strong>' in result
    assert '<span class="nav-card__description">Install the integration</span>' in result


def test_navigation_card_uses_resolver_repaired_target(tmp_path):
    markdown = tmp_path / "markdown"
    source = markdown / "pub" / "source.md"
    target = markdown / "pub" / "moved" / "vault.md"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text("# Source", encoding="utf-8")
    target.write_text("# Vault", encoding="utf-8")
    resolver = FamilyLinkResolver(markdown, "australia")
    text = '''<table class="nav-card"><tr><td>

[Vault\\[Omitted image "vault.svg"\\] Alt text:Protect sensitive data.](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/old/vault.md)

</td></tr></table>'''

    result = transform_document(
        text,
        "australia",
        PurePosixPath("pub/source.md"),
        {"australia"},
        "source",
        resolver=resolver,
    )

    assert 'href="../moved/vault/"' in result
    assert resolver.report()["counts"]["document_links"]["repaired"] == 1


def test_unrecognized_navigation_card_is_preserved():
    table = '<table class="nav-card"><tr><td>[Ordinary link](target.md)</td></tr></table>'
    assert transform_navigation_cards(table, PurePosixPath("pub/page.md")) == table


def test_ordinary_omitted_image_and_non_navigation_table_keep_existing_behavior():
    text = '<table><tr><td>\\[Omitted image "plain.svg"\\] Alt text:Plain notice</td></tr></table>'
    result = transform_document(
        text, "australia", PurePosixPath("pub/page.md"), {"australia"}, "source"
    )
    assert '<table><tr><td>' in result
    assert "Image omitted" in result and "Plain notice" in result


def test_inline_markdown_in_ordinary_html_table_cells_is_rendered():
    text = """<table><tr><th>Details</th><td>
See [Domain scope](../security/domain.md) and **review the requirements**.
</td></tr></table>"""

    result = transform_document(
        text,
        "australia",
        PurePosixPath("api/page.md"),
        {"australia"},
        "source",
    )

    assert '<a href="../../security/domain/">Domain scope</a>' in result
    assert "<strong>review the requirements</strong>" in result
    assert "[Domain scope]" not in result


def test_indented_list_markdown_inside_table_cell_does_not_become_code():
    table = """<table><tr><td>
**Note:** Values are populated if:

    -   See [Data source](data.md).
    -   See [Mapper](mapper.md).
</td></tr></table>"""

    result = transform_table_markdown(table, PurePosixPath("pub/page.md"))

    assert "<ul>" in result
    assert "<pre><code>" not in result
    assert 'href="../data/"' in result


def test_fenced_code_inside_table_cell_is_consumed_locally():
    table = """<table><tr><td>
Example:
```
value = "[not a link](example.md)"
```
</td></tr></table>"""
    result = transform_table_markdown(table, PurePosixPath("pub/page.md"))
    assert "<div class=\"highlight\">" in result
    assert result.count("```") == 0


def test_markdown_table_nested_inside_raw_table_gets_real_links():
    table = """<table><tr><td>
<table><tr><td>Inner</td></tr></table>
|API|Details|
|---|---|
|[Attachment API](https://example.com/api)|Changed|
</td></tr></table>"""
    result = transform_table_markdown(table, PurePosixPath("pub/page.md"))
    assert '<a href="https://example.com/api">Attachment API</a>' in result
    assert "[Attachment API]" not in result


def test_table_markdown_uses_link_resolver_and_records_repair(tmp_path):
    markdown_root = tmp_path / "markdown"
    current = markdown_root / "pub" / "page.md"
    target = markdown_root / "pub" / "moved" / "target.md"
    current.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    current.write_text("# Page", encoding="utf-8")
    target.write_text("# Target", encoding="utf-8")
    resolver = FamilyLinkResolver(markdown_root, "australia")

    result = transform_table_markdown(
        "<table><tr><td>[Target](old/target.md)</td></tr></table>",
        PurePosixPath("pub/page.md"),
        resolver,
    )

    assert 'href="../moved/target/"' in result
    assert resolver.report()["counts"]["document_links"]["repaired"] == 1


def test_unrecognized_navigation_card_is_not_changed_by_table_markdown():
    table = '<table class="presentation nav-card"><tr><td>[Ordinary](target.md)</td></tr></table>'
    assert transform_table_markdown(table, PurePosixPath("pub/page.md")) == table


def test_plain_and_malformed_table_cells_are_preserved():
    table = "<table><tr><td>Plain [unfinished text</td><td>C:\\temp</td></tr></table>"
    assert transform_table_markdown(table, PurePosixPath("pub/page.md")) == table + "\n\n"


def test_table_closing_tag_is_separated_from_following_markdown():
    result = transform_table_markdown(
        "<table><tr><td>Value</td></tr></table>## Next heading",
        PurePosixPath("pub/page.md"),
    )
    assert "</table>\n\n## Next heading" in result


def test_fenced_code_markers_receive_block_boundaries():
    text = "Before ```python\ncode\n```\n## After\n"
    assert normalize_fenced_code_boundaries(text) == (
        "Before\n\n```python\ncode\n\n```\n## After\n"
    )


def test_split_navigation_card_markup_becomes_one_semantic_card():
    text = """<table class="nav-card"><tr><td>
[Use](use.md)
[\\[Omitted image "use.svg"\\] Alt text:](use.md)
[Learn how to use the workspace](use.md)
</td></tr></table>"""
    result = transform_navigation_cards(text, PurePosixPath("pub/index.md"))
    assert result.count('class="nav-card__item"') == 1
    assert '<strong class="nav-card__title">Use</strong>' in result
    assert '<span class="nav-card__description">Learn how to use the workspace</span>' in result
