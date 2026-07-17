from pathlib import PurePosixPath

import pytest

from sndocs.links import AmbiguousLinkError, FamilyLinkResolver


def markdown_tree(tmp_path, paths):
    root = tmp_path / "markdown"
    for value in paths:
        path = root / value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}", encoding="utf-8")
    return root


def test_exact_target_is_unchanged(tmp_path):
    root = markdown_tree(tmp_path, ["pub/page.md"])
    resolver = FamilyLinkResolver(root, "australia")
    assert resolver.resolve("pub/page.md", PurePosixPath("other/source.md")) == PurePosixPath("pub/page.md")
    assert resolver.report()["counts"]["exact"] == 1


def test_unique_moved_target_is_repaired(tmp_path):
    root = markdown_tree(tmp_path, ["servicenow-platform/multi-instance-framework-hermes/hermes-messaging-service.md"])
    resolver = FamilyLinkResolver(root, "australia")
    resolved = resolver.resolve(
        "servicenow-platform/hermes-messaging-service.md", PurePosixPath("telecom/source.md")
    )
    assert resolved == PurePosixPath(
        "servicenow-platform/multi-instance-framework-hermes/hermes-messaging-service.md"
    )
    assert resolver.report()["repairs"][0]["method"] == "unique-basename"


def test_same_publication_disambiguates_duplicate_basename(tmp_path):
    root = markdown_tree(tmp_path, ["pub/new/page.md", "other/page.md"])
    resolver = FamilyLinkResolver(root, "australia")
    assert resolver.resolve("pub/page.md", PurePosixPath("source.md")) == PurePosixPath("pub/new/page.md")
    assert resolver.report()["repairs"][0]["method"] == "same-publication"


def test_unresolved_ambiguity_fails_with_context(tmp_path):
    root = markdown_tree(tmp_path, ["one/page.md", "two/page.md"])
    resolver = FamilyLinkResolver(root, "australia")
    with pytest.raises(AmbiguousLinkError, match=r"source\.md.*one/page\.md.*two/page\.md"):
        resolver.resolve("missing/page.md", PurePosixPath("source.md"))


def test_missing_target_is_aggregated_by_referring_page(tmp_path):
    root = markdown_tree(tmp_path, ["pub/source.md"])
    resolver = FamilyLinkResolver(root, "australia")
    resolver.resolve("pub/missing.md", PurePosixPath("pub/source.md"))
    resolver.resolve("pub/missing.md", PurePosixPath("other/source.md"))
    report = resolver.report()
    assert report["counts"]["placeholder"] == 1
    assert report["placeholders"][0]["referring_pages"] == ["other/source.md", "pub/source.md"]

