import hashlib
import json
import tarfile
import zipfile

from sndocs.artifacts import package_site


def test_archives_have_identical_trees_and_valid_checksums(tmp_path):
    site = tmp_path / "site"
    (site / "australia").mkdir(parents=True)
    (site / "australia" / "index.html").write_text("ok", encoding="utf-8")
    manifest = {"latest": "australia", "families": {"australia": {"archived": False}}}
    (site / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (site / "versions.json").write_text(json.dumps({"latest": "australia", "versions": []}), encoding="utf-8")
    outputs = package_site(site, tmp_path / "out", "sndocs-site")
    tar_path, zip_path = outputs[:2]
    with tarfile.open(tar_path) as tar, zipfile.ZipFile(zip_path) as archive:
        assert sorted(tar.getnames()) == sorted(archive.namelist())
    for archive, checksum in ((tar_path, outputs[2]), (zip_path, outputs[3])):
        assert checksum.read_text().split()[0] == hashlib.sha256(archive.read_bytes()).hexdigest()

