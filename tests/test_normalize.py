"""Unit tests for the render-equivalent cosmetic pass in ``sndocs.normalize``.

Focused on issue #26: redundant ``\\(`` / ``\\)`` / ``\\_`` escapes inside raw
HTML ``<table>`` blocks must be stripped, while every other cosmetic cleanup
keeps its existing ``in_table`` behaviour.
"""

from __future__ import annotations

from sndocs.normalize import cosmetic_candidate, normalize_text, parser


def test_strips_paren_and_word_underscore_escapes_inside_raw_html_table() -> None:
    text = (
        "<table>\n"
        "<tr><td>call foo\\(bar\\) then field\\_name</td></tr>\n"
        "</table>\n"
    )
    out, stats = cosmetic_candidate(text)
    assert "call foo(bar) then field_name" in out
    assert "\\(" not in out and "\\)" not in out and "\\_" not in out
    assert stats["redundant_escapes_removed"] == 3


def test_leaves_non_word_underscore_escape_inside_table() -> None:
    text = "<table>\n<tr><td>see \\_ marker</td></tr>\n</table>\n"
    out, stats = cosmetic_candidate(text)
    assert "\\_ marker" in out
    assert stats["redundant_escapes_removed"] == 0


def test_leaves_other_escapes_untouched_inside_table() -> None:
    text = "<table>\n<tr><td>a\\-b and \\* star and \\#hash</td></tr>\n</table>\n"
    out, _ = cosmetic_candidate(text)
    assert "a\\-b and \\* star and \\#hash" in out


def test_trailing_whitespace_still_suppressed_inside_table() -> None:
    text = "<table>\n<tr><td>foo</td></tr>   \n</table>\n"
    out, stats = cosmetic_candidate(text)
    assert "<tr><td>foo</td></tr>   " in out
    assert stats["trailing_space_lines_cleaned"] == 0


def test_indented_html_table_lines_are_left_alone() -> None:
    # Four-space indent => indented code block; escapes there are literal.
    text = "    <table>\n    <tr><td>foo\\(bar\\)</td></tr>\n    </table>\n"
    out, stats = cosmetic_candidate(text)
    assert "foo\\(bar\\)" in out
    assert stats["redundant_escapes_removed"] == 0


def test_outside_table_behaviour_unchanged() -> None:
    text = "prose foo\\(bar\\) and field\\_name and trailing \n"
    out, stats = cosmetic_candidate(text)
    assert "prose foo(bar) and field_name and trailing\n" in out
    assert stats["redundant_escapes_removed"] == 3
    assert stats["trailing_space_lines_cleaned"] == 1


def test_full_normalize_strips_table_escapes_and_stays_render_equivalent() -> None:
    md = parser()
    src = (
        "---\ntitle: T\n---\n\n"
        "# T\n\n"
        "<table>\n"
        "<tr><th>Name</th><th>Detail</th></tr>\n"
        "<tr><td>getValue\\(\\)</td><td>the user\\_name field</td></tr>\n"
        "</table>\n"
    )
    normalized, stats, errors = normalize_text(src, md, "api/x.md", frozenset())
    assert errors == []
    assert "getValue()" in normalized
    assert "the user_name field" in normalized
    assert "\\(" not in normalized and "\\)" not in normalized
    assert stats["redundant_escapes_removed"] >= 3
    # Second pass is byte-identical (idempotence).
    again, _, again_errors = normalize_text(
        normalized, md, "api/x.md", frozenset(), audit_idempotence=False
    )
    assert again_errors == []
    assert again == normalized
