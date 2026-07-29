import hashlib
import json
import tarfile
import zipfile

import pytest

from sndocs.artifacts import package_site, validate_site
from sndocs.builder import empty_link_counts


def test_archives_have_identical_trees_and_valid_checksums(tmp_path):
    site = tmp_path / "site"
    (site / "australia").mkdir(parents=True)
    (site / "australia" / "index.html").write_text("ok", encoding="utf-8")
    pagefind = site / "australia" / "pagefind"
    (pagefind / "index").mkdir(parents=True)
    for name in (
        "pagefind.js",
        "pagefind-entry.json",
        "pagefind-component-ui.js",
        "pagefind-component-ui.css",
    ):
        (pagefind / name).write_text("ok", encoding="utf-8")
    (pagefind / "index" / "en_fixture.pf_index").write_text("ok", encoding="utf-8")
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


def _write_validated_site(tmp_path, *, profile="production", archived=False):
    site = tmp_path / "site"
    family = site / "australia"
    family.mkdir(parents=True)
    (family / "index.html").write_text("ok", encoding="utf-8")
    counts = empty_link_counts()
    manifest = {
        "build_profile": profile,
        "latest": "australia",
        "families": {
            "australia": {"archived": archived, "link_counts": counts}
        },
    }
    (site / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (site / "versions.json").write_text(
        json.dumps({"latest": "australia", "versions": []}), encoding="utf-8"
    )
    (site / "link-report.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "families": {"australia": {"counts": counts}},
            }
        ),
        encoding="utf-8",
    )
    return site, family


def test_validation_requires_pagefind_for_current_production_family(tmp_path):
    site, _family = _write_validated_site(tmp_path)

    with pytest.raises(ValueError, match="has no Pagefind search bundle"):
        validate_site(site)


def test_validation_rejects_legacy_search_for_current_production_family(tmp_path):
    site, family = _write_validated_site(tmp_path)
    pagefind = family / "pagefind"
    (pagefind / "index").mkdir(parents=True)
    for name in (
        "pagefind.js",
        "pagefind-entry.json",
        "pagefind-component-ui.js",
        "pagefind-component-ui.css",
    ):
        (pagefind / name).write_text("ok", encoding="utf-8")
    (pagefind / "index" / "en_fixture.pf_index").write_text("ok", encoding="utf-8")
    (family / "search").mkdir()
    (family / "search" / "search_index.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="retains a legacy Material search index"):
        validate_site(site)


def test_validation_keeps_archived_search_output_immutable(tmp_path):
    site, family = _write_validated_site(tmp_path, archived=True)
    (family / "search").mkdir()
    (family / "search" / "search_index.json").write_text("{}", encoding="utf-8")

    validate_site(site)


def test_validation_requires_smoke_family_to_omit_search(tmp_path):
    site, family = _write_validated_site(tmp_path, profile="smoke")
    validate_site(site)
    (family / "pagefind").mkdir()
    (family / "pagefind" / "pagefind.js").write_text("ok", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpectedly contains search output"):
        validate_site(site)
