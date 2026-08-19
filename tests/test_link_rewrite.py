from sndocs.link_rewrite import rewrite_links


def test_rewrites_raw_github_link_to_in_corpus_target() -> None:
    text = "See [the other page](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/category-one/html-table.md)."
    known_paths = frozenset({"markdown/category-one/pipe-table.md", "markdown/category-one/html-table.md"})

    rewritten, stats = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == "See [the other page](html-table.md)."
    assert stats["raw_github_links_rewritten"] == 1


def test_rewrites_across_categories_with_relative_path() -> None:
    text = "[target](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/category-two/page.md)"
    known_paths = frozenset({"markdown/category-one/pipe-table.md", "markdown/category-two/page.md"})

    rewritten, _ = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == "[target](../category-two/page.md)"


def test_leaves_raw_github_link_untouched_when_target_not_in_corpus() -> None:
    text = "[missing](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/category-one/does-not-exist.md)"
    known_paths = frozenset({"markdown/category-one/pipe-table.md"})

    rewritten, stats = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == text
    assert stats["raw_github_links_rewritten"] == 0


def test_leaves_non_matching_external_link_untouched() -> None:
    text = "[ServiceNow](https://www.servicenow.com)"
    known_paths = frozenset({"markdown/category-one/pipe-table.md"})

    rewritten, stats = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == text
    assert stats["raw_github_links_rewritten"] == 0


def test_leaves_non_matching_github_url_shapes_untouched() -> None:
    text = (
        "[blob link](https://github.com/ServiceNow/ServiceNowDocs/blob/australia/markdown/category-one/html-table.md) "
        "[wrong branch](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/store/markdown/category-one/html-table.md)"
    )
    known_paths = frozenset({"markdown/category-one/html-table.md"})

    rewritten, stats = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == text
    assert stats["raw_github_links_rewritten"] == 0


def test_preserves_fragment_when_rewriting() -> None:
    text = "[section](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/category-one/html-table.md#some-section)"
    known_paths = frozenset({"markdown/category-one/pipe-table.md", "markdown/category-one/html-table.md"})

    rewritten, _ = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == "[section](html-table.md#some-section)"


def test_rewrites_link_to_itself_as_bare_filename() -> None:
    text = "[here](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/category-one/pipe-table.md)"
    known_paths = frozenset({"markdown/category-one/pipe-table.md"})

    rewritten, _ = rewrite_links(text, known_paths, "markdown/category-one/pipe-table.md")

    assert rewritten == "[here](pipe-table.md)"
