import json

from sndocs.builder import read_manifest


def test_manifest_retains_archived_family_shape(tmp_path):
    site = tmp_path / "previous"
    site.mkdir()
    expected = {"families": {"xanadu": {"source_sha": "abc", "archived": True}}}
    (site / "build-manifest.json").write_text(json.dumps(expected), encoding="utf-8")
    assert read_manifest(site) == expected

