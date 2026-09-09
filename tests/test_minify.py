"""Unit coverage for `sndocs.minify` — the conservative option set (which
`sndocs.minify_check`, #33, is meant to import from here) and the parallel walk's
per-file error handling."""

from pathlib import Path

from sndocs.minify import MINIFY_OPTIONS, minify_html_text, minify_site


def test_minify_options_are_the_conservative_profile() -> None:
    # Spelled out so #33 can rely on importing exactly this, and so a future
    # minify-html default flip can't silently change our profile.
    assert MINIFY_OPTIONS == {
        "keep_closing_tags": True,
        "keep_html_and_head_opening_tags": True,
        "keep_comments": False,
        "minify_css": False,
        "minify_js": False,
        "minify_doctype": False,
        "allow_noncompliant_unquoted_attribute_values": False,
        "allow_optimal_entities": False,
        "allow_removing_spaces_between_attributes": False,
    }


def test_minify_html_text_collapses_inter_tag_whitespace_but_keeps_structure() -> None:
    out = minify_html_text("<html><head></head><body>  <p>hi</p>\n\n  <p>bye</p>  </body></html>")
    assert out == "<html><head></head><body><p>hi</p><p>bye</p></body></html>"


def test_minify_html_text_does_not_fold_entity_prefixed_query_params() -> None:
    out = minify_html_text('<a href="/s?q=1&sect=2&para=3">x</a>')
    assert "&sect=2&para=3" in out


def test_minify_site_shrinks_html_and_tallies_a_poison_file(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    good = tmp_path / "sub" / "page.html"
    good.write_text("<html><head></head><body>  <p>hi</p>   </body></html>", encoding="utf-8")
    good_before = good.stat().st_size
    poison = tmp_path / "poison.html"
    poison.write_bytes(b"\xff\xfe not utf-8")
    # A non-.html file must be left alone entirely.
    (tmp_path / "keep.txt").write_text("  spaces  ", encoding="utf-8")

    report = minify_site(tmp_path, workers=1)

    assert report.total_files == 2
    assert report.minified_files == 1
    assert report.failed_files == 1
    assert report.failures[0][0] == "poison.html"
    assert report.bytes_saved > 0
    assert good.stat().st_size < good_before
    assert poison.read_bytes() == b"\xff\xfe not utf-8"
    assert (tmp_path / "keep.txt").read_text() == "  spaces  "
