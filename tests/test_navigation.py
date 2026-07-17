from sndocs.navigation import parse_index


def test_nested_index_becomes_mkdocs_navigation():
    text = '''
- [Parent](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/parent.md) -- summary
  - [Child](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/deep/child.md)
    - [Grandchild](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/deep/grand.md)
- [Leaf](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/pub/leaf.md)
'''
    assert parse_index(text) == [
        {"Parent": ["pub/parent.md", {"Child": ["pub/deep/child.md", {"Grandchild": "pub/deep/grand.md"}]}]},
        {"Leaf": "pub/leaf.md"},
    ]

