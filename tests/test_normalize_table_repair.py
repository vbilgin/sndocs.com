"""Unit tests for issue #27 — repairing residual malformed table/fence
boundaries (ADR 0001 finding 3).

* 3b: ``</table>`` followed by a fence on the *next* line (not just the same
  line) gets a blank line inserted so the fence renders as a code block.
* 3a: a single-column caption row glued directly onto a pipe-table header gets
  a blank line inserted so Python-Markdown's stricter ``tables`` extension still
  renders the table. Other ragged shapes are left untouched, not guessed at.
"""

from __future__ import annotations

import pytest

from sndocs.engine_check import check_body, python_markdown
from sndocs.normalize import (
    normalize_text,
    parser,
    pipe_row_cells,
    repair_pipe_table_captions,
    repair_table_boundaries,
    split_front_matter,
)

MD = parser()


def _repair(chunk: str) -> tuple[str, dict[str, int]]:
    repaired, stats = repair_table_boundaries(chunk)
    return repaired, {key: value for key, value in stats.items() if value}


# --------------------------------------------------------------------------- 3b


def test_fence_on_next_line_after_table_gets_blank_line() -> None:
    chunk = "<table><tr><td>x</td></tr></table>\n```js\nvar x = 1;\n```\n"
    repaired, stats = _repair(chunk)
    assert repaired == "<table><tr><td>x</td></tr></table>\n\n```js\nvar x = 1;\n```\n"
    assert stats == {"table_fence_newline_boundaries_repaired": 1}


def test_tilde_fence_on_next_line_after_table_gets_blank_line() -> None:
    repaired, stats = _repair("</table>\n~~~\ncode\n~~~\n")
    assert repaired == "</table>\n\n~~~\ncode\n~~~\n"
    assert stats == {"table_fence_newline_boundaries_repaired": 1}


def test_indented_fence_after_table_keeps_its_indent() -> None:
    repaired, _ = _repair("</table>\n   ```\ncode\n```\n")
    assert repaired == "</table>\n\n   ```\ncode\n```\n"


def test_tab_indented_fence_after_table_is_not_treated_as_a_fence() -> None:
    # A leading tab is 4 columns => indented code, not a fence (matches FENCE_RE).
    chunk = "</table>\n\t```\ncode\n```\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_same_line_fence_after_table_still_repaired() -> None:
    repaired, stats = _repair("</table>```\ncode\n```\n")
    assert repaired == "</table>\n\n```\ncode\n```\n"
    assert stats == {"table_fence_boundaries_repaired": 1}


def test_already_separated_fence_is_untouched() -> None:
    chunk = "</table>\n\n```\ncode\n```\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_indented_code_block_after_table_is_not_treated_as_a_fence() -> None:
    chunk = "</table>\n    not a fence, just indented code\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_next_line_fence_repair_is_idempotent() -> None:
    once, _ = repair_table_boundaries("</table>\n```\ncode\n```\n")
    twice, _ = repair_table_boundaries(once)
    assert once == twice


def test_full_normalize_renders_next_line_fence_as_code_block() -> None:
    src = (
        "---\ntitle: T\n---\n\n# T\n\n"
        "<table>\n<tr><td>run this</td></tr>\n</table>\n"
        "```\nGet-Item\n```\n"
    )
    normalized, _, errors = normalize_text(src, MD, "r/x.md", frozenset())
    assert errors == []
    _, body, _ = split_front_matter(normalized)
    rendered = python_markdown().convert(body)
    assert "<pre>" in rendered and "<code>" in rendered
    assert "<p>```" not in rendered
    again, _, again_errors = normalize_text(
        normalized, MD, "r/x.md", frozenset(), audit_idempotence=False
    )
    assert again_errors == []
    assert again == normalized


# --------------------------------------------------------------------------- 3a


def test_single_column_caption_row_is_split_from_the_header() -> None:
    chunk = "| Sybase Data Types |\n| Sybase | ServiceNow |\n| --- | --- |\n| int | Integer |\n"
    repaired, stats = _repair(chunk)
    assert repaired == (
        "| Sybase Data Types |\n\n| Sybase | ServiceNow |\n| --- | --- |\n| int | Integer |\n"
    )
    assert stats == {"pipe_table_caption_rows_split": 1}


def test_caption_split_makes_python_markdown_render_the_table() -> None:
    body = "| Sybase Data Types |\n| Sybase | ServiceNow |\n| --- | --- |\n| int | Integer |\n"
    # Before: the delimiter row leaks into a <p>.
    assert "<table" not in python_markdown().convert(body)
    normalized, _, errors = normalize_text(
        "---\ntitle: T\n---\n\n# T\n\n" + body, MD, "r/x.md", frozenset()
    )
    assert errors == []
    _, normalized_body, _ = split_front_matter(normalized)
    rendered = python_markdown().convert(normalized_body)
    assert "<table" in rendered
    assert "<p>| --- | --- |" not in rendered


def test_caption_split_clears_the_engine_check_table_not_rendered_finding() -> None:
    body = "| Sybase Data Types |\n| Sybase | ServiceNow |\n| --- | --- |\n| int | Integer |\n"
    findings = check_body("r/x.md", body, markdown_it=MD, python_md=python_markdown())
    assert findings == []


def test_legitimate_single_column_table_is_left_alone() -> None:
    chunk = "| Header |\n| --- |\n| row one |\n| row two |\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_header_delimiter_column_mismatch_is_left_alone() -> None:
    # Neither markdown-it-py nor Python-Markdown render this; there is no
    # non-guessing repair, so the normalizer must not touch it.
    chunk = "| A | B | C |\n| --- | --- |\n| x | y | z |\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_already_separated_caption_is_left_alone() -> None:
    chunk = "| Sybase Data Types |\n\n| Sybase | ServiceNow |\n| --- | --- |\n| int | Integer |\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_single_column_row_inside_a_table_is_not_treated_as_a_caption() -> None:
    chunk = "| a | b |\n| --- | --- |\n| c |\n| d | e |\n| --- | --- |\n| f | g |\n"
    repaired, stats = _repair(chunk)
    assert repaired == chunk
    assert stats == {}


def test_caption_that_is_itself_a_delimiter_row_is_not_split() -> None:
    chunk = "| --- |\n| Sybase | ServiceNow |\n| --- | --- |\n| int | Integer |\n"
    repaired, _ = repair_pipe_table_captions(chunk)
    assert repaired == chunk


def test_caption_split_is_idempotent() -> None:
    chunk = "| Caption |\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    once, _ = repair_pipe_table_captions(chunk)
    twice, _ = repair_pipe_table_captions(once)
    assert once == twice


def test_full_normalize_caption_split_is_idempotent() -> None:
    src = (
        "---\ntitle: T\n---\n\n# T\n\n"
        "| Sybase Data Types |\n| Sybase | ServiceNow |\n| --- | --- |\n"
        "| int | Integer |\n| char | String |\n"
    )
    normalized, stats, errors = normalize_text(src, MD, "r/x.md", frozenset())
    assert errors == []
    assert stats["pipe_table_caption_rows_split"] == 1
    again, _, again_errors = normalize_text(
        normalized, MD, "r/x.md", frozenset(), audit_idempotence=False
    )
    assert again_errors == []
    assert again == normalized


# ------------------------------------------------------------------ pipe_row_cells


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("| a | b |", ["a", "b"]),
        ("  | one |  ", ["one"]),
        (r"| a \| b | c |", [r"a \| b", "c"]),
        ("| |", [""]),
        ("no pipes here", []),
        ("| missing trailing", []),
        ("|", []),
    ],
)
def test_pipe_row_cells(line: str, expected: list[str]) -> None:
    assert pipe_row_cells(line) == expected
