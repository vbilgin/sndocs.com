from pathlib import PurePosixPath

import pytest

from sndocs.links import AmbiguousLinkError, FamilyLinkResolver, canonical_source_path


def markdown_tree(tmp_path, paths):
    root = tmp_path / "markdown"
    for value in paths:
        path = root / value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}", encoding="utf-8")
    return root


def markdown_tree_with_metadata(tmp_path, documents):
    root = tmp_path / "markdown"
    for value, metadata in documents.items():
        path = root / value
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = "\n".join(f"{key}: {item}" for key, item in metadata.items())
        path.write_text(f"---\n{fields}\n---\n\n# {path.stem}", encoding="utf-8")
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


def test_explicit_override_disambiguates_known_upstream_defect(tmp_path):
    root = markdown_tree(
        tmp_path,
        [
            "build-workflows/approvals/r_ApprovalSummarizerFormatter.md",
            "servicenow-platform/approvals/r_ApprovalSummarizerFormatter.md",
        ],
    )
    resolver = FamilyLinkResolver(root, "australia")
    resolved = resolver.resolve(
        "platform-administration/r_ApprovalSummarizerFormatter.md",
        PurePosixPath("platform-administration/c_Formatters.md"),
    )
    assert resolved == PurePosixPath(
        "servicenow-platform/approvals/r_ApprovalSummarizerFormatter.md"
    )
    assert resolver.report()["repairs"][0]["method"] == "explicit-override"


def test_self_canonical_disambiguates_source_to_pay_glossary_from_any_page(tmp_path):
    canonical = (
        "https://www.servicenow.com/docs/r/source-to-pay-operations/"
        "source-to-pay-integration-framework/source-to-pay-integrations-glossary.html"
    )
    root = markdown_tree_with_metadata(
        tmp_path,
        {
            "source-to-pay-operations/source-to-pay-integration-framework/"
            "source-to-pay-integrations-glossary.md": {"canonical_url": canonical},
            "source-to-pay-operations/source-to-pay-operations/"
            "source-to-pay-integrations-glossary.md": {},
        },
    )
    resolver = FamilyLinkResolver(root, "australia")
    expected = PurePosixPath(
        "source-to-pay-operations/source-to-pay-integration-framework/"
        "source-to-pay-integrations-glossary.md"
    )
    target = "source-to-pay-operations/source-to-pay-integrations-glossary.md"
    assert resolver.resolve(target, PurePosixPath("source-to-pay-operations/index.md")) == expected
    assert resolver.resolve(target, PurePosixPath("other/arbitrary-page.md")) == expected
    assert [repair["method"] for repair in resolver.report()["repairs"]] == [
        "self-canonical", "self-canonical"
    ]


def test_self_canonical_disambiguates_another_upstream_pattern(tmp_path):
    root = markdown_tree_with_metadata(
        tmp_path,
        {
            "integrate-applications/integration-hub/fhir-spoke-landing.md": {
                "canonical_url": (
                    "https://www.servicenow.com/docs/r/integrate-applications/"
                    "integration-hub/fhir-spoke-landing.html"
                )
            },
            "healthcare-and-life-sciences/fhir-spoke-landing.md": {},
        },
    )
    resolver = FamilyLinkResolver(root, "australia")
    resolved = resolver.resolve("missing/fhir-spoke-landing.md", PurePosixPath("source.md"))
    assert resolved == PurePosixPath("integrate-applications/integration-hub/fhir-spoke-landing.md")
    assert resolver.report()["repairs"][0]["method"] == "self-canonical"


def test_self_canonical_uses_fallback_frontmatter_parser(tmp_path):
    root = markdown_tree_with_metadata(
        tmp_path,
        {
            "pub/new/page.md": {
                "title": "Invalid: unquoted title",
                "canonical_url": "https://www.servicenow.com/docs/r/pub/new/page.html",
            },
            "pub/old/page.md": {},
        },
    )
    resolver = FamilyLinkResolver(root, "australia")
    assert resolver.resolve("pub/page.md", PurePosixPath("source.md")) == PurePosixPath(
        "pub/new/page.md"
    )


def test_multiple_self_canonical_candidates_remain_ambiguous(tmp_path):
    root = markdown_tree_with_metadata(
        tmp_path,
        {
            "one/page.md": {"canonical_url": "https://www.servicenow.com/docs/r/one/page.html"},
            "two/page.md": {"canonical_url": "https://www.servicenow.com/docs/r/two/page.html"},
        },
    )
    resolver = FamilyLinkResolver(root, "australia")
    with pytest.raises(AmbiguousLinkError):
        resolver.resolve("missing/page.md", PurePosixPath("source.md"))


@pytest.mark.parametrize(
    "canonical",
    [
        "https://example.com/docs/r/one/page.html",
        "https://www.servicenow.com/other/one/page.html",
        "not a URL",
        "https://[invalid/docs/r/one/page.html",
        "https://www.servicenow.com/docs/r/different/page.html",
    ],
)
def test_unusable_canonical_metadata_does_not_disambiguate(tmp_path, canonical):
    root = markdown_tree_with_metadata(
        tmp_path,
        {
            "one/page.md": {"canonical_url": canonical},
            "two/page.md": {},
        },
    )
    resolver = FamilyLinkResolver(root, "australia")
    with pytest.raises(AmbiguousLinkError):
        resolver.resolve("missing/page.md", PurePosixPath("source.md"))


def test_canonical_source_path_removes_upstream_markdown_escapes():
    assert canonical_source_path(
        "https://www.servicenow.com/docs/r/platform-administration/r\\_ApprovalSummarizerFormatter.html"
    ) == PurePosixPath("platform-administration/r_ApprovalSummarizerFormatter.md")


def test_explicit_override_requires_existing_destination(tmp_path):
    root = markdown_tree(
        tmp_path,
        [
            "build-workflows/approvals/r_ApprovalSummarizerFormatter.md",
            "other/approvals/r_ApprovalSummarizerFormatter.md",
        ],
    )
    resolver = FamilyLinkResolver(root, "australia")
    with pytest.raises(ValueError, match=r"override target does not exist.*servicenow-platform"):
        resolver.resolve(
            "platform-administration/r_ApprovalSummarizerFormatter.md",
            PurePosixPath("platform-administration/c_Formatters.md"),
        )


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
