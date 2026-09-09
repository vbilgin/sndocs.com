"""Pinning coverage for `sndocs.minify_check` — the before/after equivalence
checker guarding `sndocs build --minify` (issue #33).

Each check is exercised with a known-good pair (original vs its *real*
`sndocs.minify` output, which must verify clean) and a known-divergent pair
(original vs a hand-crafted "minified" string standing in for a regressed
minifier, which must be caught and drive a non-zero exit). Two of those
divergent cases are the concrete `minify-html` bugs the ticket calls out:
issue #169 (`&sect=` / `&para=` query-param decoding) and issue #192
(self-closing inline SVG emitted unclosed).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sndocs.minify
from sndocs import minify_check
from sndocs.minify import minify_html_text

DOC = "<html><head><title>t</title></head><body>{}</body></html>"


def _kinds(original: str, minified: str) -> list[str]:
    return [d.kind for d in minify_check.compare_html("p.html", original, minified)]


# --- the conservative profile is imported, never recopied (AC) ----------------


def test_profile_is_imported_from_the_minify_module_not_redeclared() -> None:
    # Both the option set and the function that applies it are the very objects
    # from sndocs.minify (identity, not just equality) — no second copy here.
    assert minify_check.MINIFY_OPTIONS is sndocs.minify.MINIFY_OPTIONS
    assert minify_check.minify_html_text is sndocs.minify.minify_html_text


# --- inter-element whitespace is the one tolerated difference -----------------


def test_pretty_printed_vs_real_minified_output_verifies_clean() -> None:
    original = DOC.format(
        "\n  <h1>Title</h1>\n  <p>One   two\n  three.</p>\n"
        '  <ul>\n    <li><a href="/a/">A</a></li>\n    <li><a href="/b/">B</a></li>\n  </ul>\n'
    )
    assert minify_html_text(original) != original  # minification did something
    assert _kinds(original, minify_html_text(original)) == []


def test_inter_element_whitespace_removal_alone_is_not_flagged() -> None:
    original = DOC.format("<p>a</p>\n\n  <p>b</p>\n  <p>c</p>")
    minified = DOC.format("<p>a</p><p>b</p><p>c</p>")
    assert _kinds(original, minified) == []


# --- tag-structure -----------------------------------------------------------


def test_dropped_element_is_a_tag_structure_divergence() -> None:
    original = DOC.format("<p>a</p><p>b</p>")
    minified = DOC.format("<p>a</p>")
    assert "tag-structure" in _kinds(original, minified)


def test_reparenting_that_keeps_tag_order_is_still_a_tag_structure_divergence() -> None:
    # Same flat tag sequence (b, i) both times; only the nesting differs. A
    # flat tag-name list would miss this — `_skeleton` carries depth.
    original = DOC.format("<p><b>x</b><i>y</i></p>")
    regressed = DOC.format("<p><b>x<i>y</i></b></p>")
    assert "tag-structure" in _kinds(original, regressed)


def test_safe_attribute_normalisation_is_not_a_divergence() -> None:
    # The conservative profile collapses whitespace in a space-separated class
    # and drops a redundant type="text"; neither is a divergence.
    original = DOC.format(
        '<div class="admonition   note"><input type="text" name="q"></div>'
    )
    minified = minify_html_text(original)
    assert 'class="admonition note"' in minified and "type=" not in minified
    assert _kinds(original, minified) == []


# --- text-content -----------------------------------------------------------


def test_changed_text_node_is_a_text_content_divergence() -> None:
    original = DOC.format("<p>keep this text</p>")
    minified = DOC.format("<p>keep that text</p>")
    assert "text-content" in _kinds(original, minified)


def test_collapsing_significant_whitespace_inside_text_is_tolerated() -> None:
    original = DOC.format("<p>one    two\n\tthree</p>")
    minified = DOC.format("<p>one two three</p>")
    assert _kinds(original, minified) == []


# --- link-attr: minify-html issue #169 -------------------------------------


def test_entity_prefix_query_param_survives_the_real_profile() -> None:
    original = DOC.format('<a href="/s?x=1&sect=2&para=3&notin=4">link</a>')
    minified = minify_html_text(original)
    assert "&sect=2&para=3&notin=4" in minified
    assert _kinds(original, minified) == []


def test_entity_prefix_query_param_decoded_is_a_link_attr_divergence() -> None:
    original = DOC.format('<a href="/s?x=1&sect=2&para=3">link</a>')
    regressed = DOC.format('<a href="/s?x=1§=2¶=3">link</a>')
    assert "link-attr" in _kinds(original, regressed)


def test_src_value_change_is_a_link_attr_divergence() -> None:
    original = DOC.format('<img src="/img/a.png">')
    regressed = DOC.format('<img src="/img/b.png">')
    assert "link-attr" in _kinds(original, regressed)


# --- inline-svg: minify-html issue #192 -----------------------------------


def test_self_closing_inline_svg_survives_the_real_profile() -> None:
    original = DOC.format(
        '<p>before</p>'
        '<svg viewBox="0 0 2 2"><path d="M0 0L2 2"/><circle cx="1" cy="1" r="1"/></svg>'
        '<p>after</p>'
    )
    minified = minify_html_text(original)
    assert _kinds(original, minified) == []


def test_unclosed_inline_svg_is_an_inline_svg_divergence() -> None:
    original = DOC.format(
        '<p>before</p><svg viewBox="0 0 2 2"><path d="M0 0"/></svg><p>after</p>'
    )
    # #192: the </svg> (and the <path/> self-close) go missing, so everything
    # after the <svg> gets re-parented into it.
    regressed = DOC.format(
        '<p>before</p><svg viewBox="0 0 2 2"><path d="M0 0"><p>after</p>'
    )
    assert "inline-svg" in _kinds(original, regressed)


def test_main_exits_nonzero_on_an_unclosed_inline_svg(tmp_path, monkeypatch, capsys) -> None:
    site = _write_site(
        tmp_path,
        {
            "icon.html": DOC.format(
                '<p>a</p><svg viewBox="0 0 2 2"><path d="M0 0"/></svg><p>b</p>'
            )
        },
    )
    # Stand in for minify-html #192: emit the inline SVG unclosed.
    monkeypatch.setattr(
        minify_check,
        "minify_html_text",
        lambda html: html.replace('<path d="M0 0"/></svg>', '<path d="M0 0">'),
    )

    assert minify_check.main(["--site", str(site)]) == 1
    assert "inline-svg" in capsys.readouterr().out


# --- pre-text -----------------------------------------------------------


def test_pre_whitespace_loss_is_a_pre_text_divergence() -> None:
    original = DOC.format("<pre><code>def f():\n    return 1\n</code></pre>")
    regressed = DOC.format("<pre><code>def f():\n return 1\n</code></pre>")
    assert "pre-text" in _kinds(original, regressed)


def test_pre_benign_lt_reencode_is_tolerated() -> None:
    original = DOC.format("<pre>&lt;tag attr=&quot;v&quot;&gt; &amp; more</pre>")
    minified = minify_html_text(original)
    # minify-html re-encodes the now-unambiguous `&gt;` back to a literal `>`.
    assert _kinds(original, minified) == []


# --- huge / broken input -------------------------------------------------


def test_deeply_nested_page_past_libxml2_default_limits_verifies_clean() -> None:
    # libxml2's default parser rejects trees deeper than 256; real corpus pages
    # blow past that. `_parse`'s huge_tree lifts the limit and `_skeleton` walks
    # iteratively, so both sides parse whole and compare equal without a
    # RecursionError.
    deep = "<div>" * 500 + "leaf" + "</div>" * 500
    original = DOC.format(deep)
    assert _kinds(original, minify_html_text(original)) == []


def test_empty_minified_output_is_a_parse_failure() -> None:
    original = DOC.format("<p>fine</p>")
    findings = minify_check.compare_html("p.html", original, "   ")
    assert [f.kind for f in findings] == ["parse-failure"]


# --- aggregate size reduction + exit code -----------------------------


def _write_site(root: Path, pages: dict[str, str]) -> Path:
    site = root / "site"
    for name, html in pages.items():
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    return site


def test_check_pages_reports_before_after_totals_and_reduction(tmp_path: Path) -> None:
    site = _write_site(
        tmp_path,
        {
            "index.html": DOC.format("\n  <p>hello   world</p>\n  <p>second</p>\n"),
            "guide/page.html": DOC.format("\n  <h2>Guide</h2>\n  <p>body\n  text</p>\n"),
        },
    )

    report = minify_check.check_pages(minify_check._discover(site), site)

    assert report.checked == 2
    assert report.clean
    assert report.bytes_after < report.bytes_before
    assert report.percent_reduction > 0
    assert "2 page(s)" in report.summary()
    assert "reduction" in report.summary()


def test_main_exits_zero_on_a_clean_site(tmp_path: Path) -> None:
    site = _write_site(
        tmp_path,
        {"index.html": DOC.format("\n  <p>a</p>\n  <p>b</p>\n")},
    )
    assert minify_check.main(["--site", str(site)]) == 0


def test_main_exits_nonzero_when_a_page_diverges(tmp_path: Path, monkeypatch, capsys) -> None:
    site = _write_site(
        tmp_path,
        {"index.html": DOC.format('<a href="/s?a=1&sect=2">x</a>')},
    )
    # Stand in for a regressed minifier that decodes the &sect= prefix.
    monkeypatch.setattr(
        minify_check,
        "minify_html_text",
        lambda html: html.replace("&sect=2", "§=2"),
    )

    assert minify_check.main(["--site", str(site)]) == 1
    out = capsys.readouterr().out
    assert "link-attr" in out
    assert "1 divergence(s)" in out


def test_main_errors_when_the_site_dir_is_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        minify_check.main(["--site", str(tmp_path / "nope")])
