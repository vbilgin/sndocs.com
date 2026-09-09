"""Engine re-validation (issue #14).

The normalizer only applies its "safe" cosmetic cleanup and simple HTML-table
conversion when the change is render-equivalent under `markdown-it-py`. The site
is actually rendered by MkDocs + Python-Markdown with the extension bundle in
`mkdocs.yml`. These tests pin the bundle and confirm the normalizer's
render-equivalence guarantees still hold under it — including the concrete
finding that motivated switching the stock `fenced_code` extension for
`pymdownx.superfences`.

Full findings from the one-time full-corpus sweep are in
`docs/adr/0001-rendering-engine-revalidation.md`; `python -m sndocs.engine_check`
reproduces that sweep.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sndocs.engine_check import (
    check_body,
    configured_extensions,
    python_markdown,
    render_python_markdown,
)
from sndocs.normalize import normalize_corpus
from sndocs.normalize import parser as markdown_it_parser
from sndocs.normalize import split_front_matter

REPO_ROOT = Path(__file__).resolve().parents[1]
MKDOCS_CONFIG = REPO_ROOT / "mkdocs.yml"


@pytest.fixture(scope="module")
def engine() -> "object":
    return python_markdown(MKDOCS_CONFIG)


def _render(engine, text: str) -> str:
    return render_python_markdown(engine, text)


def test_mkdocs_bundle_matches_the_revalidated_decision() -> None:
    """The bundle the ADR was validated against, pinned so a future edit that
    diverges from it fails loudly."""
    extensions, configs = configured_extensions(MKDOCS_CONFIG)

    assert "tables" in extensions
    assert "toc" in extensions
    assert "pymdownx.superfences" in extensions
    # Raw HTML must stay opaque passthrough (matches markdown-it `html:true` and
    # the normalizer's "leave complex tables as raw HTML" contract).
    assert "md_in_html" not in extensions
    # Aggressive inline-syntax extensions widen the parse surface the
    # normalizer's guarantees rest on; deliberately excluded.
    for risky in ("pymdownx.tilde", "pymdownx.caret", "pymdownx.mark", "pymdownx.smartsymbols"):
        assert risky not in extensions
    assert configs.get("toc", {}).get("permalink") is True


def test_unlabelled_fence_inside_a_list_item_renders_as_a_code_block(engine) -> None:
    """The #14 regression guard: an unlabelled ``` fence indented as list-item
    continuation (pervasive in the corpus's how-to steps). Stock `fenced_code`
    leaves the ``` markers as literal `<p>` text and renders the code as prose;
    `pymdownx.superfences` renders a real `<pre>` code block."""
    html = _render(
        engine,
        "1.  Add the script:\n"
        "\n"
        "    ```\n"
        "    var x = 1;\n"
        "\n"
        "    var y = 2;\n"
        "    ```\n"
        "\n"
        "    Done.\n",
    )

    assert "<pre" in html
    assert "```" not in html
    assert "var x = 1;" in html and "var y = 2;" in html
    assert "<p>Done.</p>" in html


def test_bare_eof_style_fence_renders_as_code(engine) -> None:
    """The bare ``` / ~~~ fences the normalizer's EOF fence closure emits still
    render as code (sanity check; passes under `fenced_code` too)."""
    for fence in ("```\nvar x = 1;\n```", "~~~\nvar x = 1;\n~~~"):
        html = _render(engine, fence)
        assert "<code>" in html and "var x = 1;" in html
        assert "```" not in html and "~~~" not in html


@pytest.mark.parametrize(
    ("escaped", "plain"),
    [
        (r"See addError\(Object message\) for details.", "See addError(Object message) for details."),
        (r"The sysparm\_query parameter is optional.", "The sysparm_query parameter is optional."),
        (r"A mix: foo\_bar and baz\(qux\) end.", "A mix: foo_bar and baz(qux) end."),
        (r"## Heading with addError\(Object message\)", "## Heading with addError(Object message)"),
    ],
)
def test_redundant_escape_cleanup_is_render_equivalent(engine, escaped: str, plain: str) -> None:
    """The escapes the normalizer strips (`\\(`, `\\)`, `\\_` between word chars)
    render identically stripped or not under the configured engine."""
    assert _render(engine, escaped) == _render(engine, plain)


def test_excess_blank_line_cleanup_is_render_equivalent(engine) -> None:
    many = "First paragraph.\n\n\n\n\n\nSecond paragraph."
    collapsed = "First paragraph.\n\nSecond paragraph."

    assert _render(engine, many) == _render(engine, collapsed)


def test_simple_html_table_conversion_renders_as_one_table(engine, fixture_corpus: Path, tmp_path: Path) -> None:
    """The fixture corpus's raw HTML table, once normalized to a pipe table,
    renders as exactly one `<table>` with the same cell text under the engine."""
    source = (fixture_corpus / "markdown" / "category-one" / "html-table.md").read_text()
    _, source_body, _ = split_front_matter(source)

    markdown_it = markdown_it_parser()
    findings = check_body("html-table.md", source_body, markdown_it=markdown_it, python_md=engine)
    assert [f.kind for f in findings] == [], findings

    # And the actually-normalized file renders one table with the data intact.
    normalize_corpus(fixture_corpus / "markdown", tmp_path / "normalized", workers=1)
    normalized = (tmp_path / "normalized" / "category-one" / "html-table.md").read_text()

    _, normalized_body, _ = split_front_matter(normalized)
    html = _render(engine, normalized_body)
    assert html.lower().count("<table") == 1
    for cell in ("Column A", "Column B", "foo", "bar", "baz", "qux"):
        assert f">{cell}<" in html


def test_fixture_corpus_normalization_holds_under_the_configured_engine(
    engine, fixture_corpus: Path
) -> None:
    """End-to-end: every fixture-corpus file's normalizer-gated transforms are
    render-equivalent (or better) under the configured Python-Markdown engine —
    no table drops, no cosmetic divergence."""
    markdown_it = markdown_it_parser()
    for source_path in sorted((fixture_corpus / "markdown").rglob("*.md")):
        _, body, _ = split_front_matter(source_path.read_text().replace("\r\n", "\n"))
        findings = check_body(source_path.name, body, markdown_it=markdown_it, python_md=engine)
        assert findings == [], f"{source_path.name}: {findings}"
