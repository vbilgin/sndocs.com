import hashlib
import json
import tarfile
import zipfile

import pytest

from sndocs.artifacts import package_site
from sndocs.builder import empty_link_counts


def test_archives_have_identical_trees_and_valid_checksums(tmp_path):
    site = tmp_path / "site"
    (site / "australia").mkdir(parents=True)
    (site / "australia" / "index.html").write_text("ok", encoding="utf-8")
    counts = empty_link_counts()
    manifest = {"latest": "australia", "families": {"australia": {"archived": False, "link_counts": counts}}}
    (site / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (site / "versions.json").write_text(json.dumps({"latest": "australia", "versions": []}), encoding="utf-8")
    (site / "link-report.json").write_text(
        json.dumps({"schema_version": 2, "families": {"australia": {"counts": counts}}}), encoding="utf-8"
    )
    outputs = package_site(site, tmp_path / "out", "sndocs-site")
    tar_path, zip_path = outputs[:2]
    with tarfile.open(tar_path) as tar, zipfile.ZipFile(zip_path) as archive:
        assert sorted(tar.getnames()) == sorted(archive.namelist())
    for archive, checksum in ((tar_path, outputs[2]), (zip_path, outputs[3])):
        assert checksum.read_text().split()[0] == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_smoke_build_cannot_be_packaged(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "build-manifest.json").write_text(
        json.dumps({"build_profile": "smoke"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="smoke builds cannot be packaged"):
        package_site(site, tmp_path / "out", "sndocs-site")
