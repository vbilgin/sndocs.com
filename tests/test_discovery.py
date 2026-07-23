import pytest

from sndocs.discovery import parse_llms


LLMS = '''
- "australia" : "australia" -- latest
- "zurich" : "zurich" -- previous
## Documents
- [Building applications](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/application-development/index.md)
- [API reference](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/api-reference/index.md)
'''


def test_parse_llms_preserves_release_and_publication_order():
    result = parse_llms(LLMS)
    assert result.families == ["australia", "zurich"]
    assert result.latest == "australia"
    assert [item.slug for item in result.publications] == ["application-development", "api-reference"]


def test_parse_llms_applies_allowlist_without_changing_source_order():
    result = parse_llms(LLMS, ("zurich",))
    assert result.families == ["zurich"]
    assert result.latest == "zurich"


def test_parse_llms_reorders_allowlist_to_match_upstream_and_rejects_unknown():
    assert parse_llms(LLMS, ("zurich", "australia")).families == ["australia", "zurich"]
    with pytest.raises(ValueError, match="unknown release families: future"):
        parse_llms(LLMS, ("future",))
