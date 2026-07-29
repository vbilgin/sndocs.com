from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sndocs.artifacts import validate_site
from sndocs.builder import empty_link_counts
from sndocs.deployment import (
    StoredObject,
    assemble_candidate,
    build_family_inventory,
    create_deterministic_archive,
    family_artifact_id,
    plan_cleanup,
    plan_latest_release,
    reconstruct_archive,
    release_id_for,
    split_archive,
    validate_candidate_root,
    validate_family_inventory,
    validate_release_manifest,
    verify_uploaded_inventory,
)

FINGERPRINT = "f" * 64


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _site(tmp_path: Path, family: str, sha: str, *, text: str = "page") -> Path:
    site = tmp_path / f"site-{family}"
    family_root = site / family
    family_root.mkdir(parents=True)
    (family_root / "index.html").write_text(text, encoding="utf-8")
    (family_root / "404.html").write_text("missing", encoding="utf-8")
    pagefind = family_root / "pagefind"
    (pagefind / "index").mkdir(parents=True)
    for name in (
        "pagefind.js",
        "pagefind-entry.json",
        "pagefind-component-ui.js",
        "pagefind-component-ui.css",
    ):
        (pagefind / name).write_text("pagefind", encoding="utf-8")
    (pagefind / "index" / "en_fixture.pf_index").write_text(
        "index", encoding="utf-8"
    )
    (site / "index.html").write_text(
        f'<meta http-equiv="refresh" content="0; url=./{family}/">',
        encoding="utf-8",
    )
    (site / "SERVICENOW-LICENSE.txt").write_text("license", encoding="utf-8")
    counts = empty_link_counts()
    _write_json(
        site / "build-manifest.json",
        {
            "schema_version": 1,
            "pipeline_version": "0",
            "pipeline_fingerprint": FINGERPRINT,
            "built_at": "2026-01-01T00:00:00+00:00",
            "upstream_repository": "ServiceNow/ServiceNowDocs",
            "build_profile": "production",
            "latest": family,
            "families": {
                family: {
                    "source_sha": sha,
                    "archived": False,
                    "path": f"/{family}/",
                    "link_counts": counts,
                }
            },
        },
    )
    _write_json(
        site / "versions.json",
        {
            "latest": family,
            "versions": [
                {
                    "family": family,
                    "title": family.title(),
                    "path": f"/{family}/",
                    "archived": False,
                }
            ],
        },
    )
    _write_json(
        site / "link-report.json",
        {
            "schema_version": 2,
            "families": {
                family: {
                    "family": family,
                    "counts": counts,
                    "repairs": [],
                    "placeholders": [],
                    "omitted_images": [],
                }
            },
        },
    )
    return site


def _release(tmp_path: Path, family: str, sha: str):
    site = _site(tmp_path, family, sha)
    inventory = build_family_inventory(
        site, family, sha, FINGERPRINT, created_at="2026-01-01T00:00:00+00:00"
    )
    root = tmp_path / f"root-{family}"
    release = assemble_candidate(
        site,
        root,
        inventory,
        created_at="2026-01-01T00:00:00+00:00",
    )
    return site, root, inventory, release


def test_planner_covers_initial_no_change_rebuild_and_new_latest(tmp_path):
    _site, _root, _inventory, active = _release(tmp_path, "yokohama", "sha-1")
    initial = plan_latest_release(
        {"latest": "yokohama", "shas": {"yokohama": "sha-1"}},
        FINGERPRINT,
        None,
    )
    unchanged = plan_latest_release(
        {"latest": "yokohama", "shas": {"yokohama": "sha-1"}},
        FINGERPRINT,
        active,
    )
    changed_sha = plan_latest_release(
        {"latest": "yokohama", "shas": {"yokohama": "sha-2"}},
        FINGERPRINT,
        active,
    )
    changed_pipeline = plan_latest_release(
        {"latest": "yokohama", "shas": {"yokohama": "sha-1"}},
        "e" * 64,
        active,
    )
    new_latest = plan_latest_release(
        {"latest": "zurich", "shas": {"zurich": "sha-3", "washington": "x"}},
        FINGERPRINT,
        active,
    )

    assert initial["action"] == "initial"
    assert unchanged["action"] == "none"
    assert not unchanged["changed"]
    assert changed_sha["action"] == "rebuild"
    assert changed_pipeline["action"] == "rebuild"
    assert new_latest["action"] == "new-latest"
    assert "washington" not in new_latest


def test_family_inventory_is_deterministic_and_rejects_corruption(tmp_path):
    site = _site(tmp_path, "zurich", "sha")
    first = build_family_inventory(
        site, "zurich", "sha", FINGERPRINT, created_at="now"
    )
    second = build_family_inventory(
        site, "zurich", "sha", FINGERPRINT, created_at="later"
    )
    assert first["artifact_id"] == second["artifact_id"]
    assert first["tree_sha256"] == second["tree_sha256"]
    assert first["artifact_id"] == family_artifact_id("zurich", "sha", FINGERPRINT)

    corrupted = copy.deepcopy(first)
    corrupted["objects"][0]["bytes"] += 1
    with pytest.raises(ValueError, match="byte count"):
        validate_family_inventory(corrupted)


def test_candidate_archives_only_previously_published_families(tmp_path):
    _old_site, old_root, _old_inventory, active = _release(
        tmp_path, "yokohama", "sha-1"
    )
    new_site = _site(tmp_path, "zurich", "sha-2")
    new_inventory = build_family_inventory(
        new_site, "zurich", "sha-2", FINGERPRINT, created_at="now"
    )
    candidate_root = tmp_path / "candidate"
    candidate = assemble_candidate(
        new_site,
        candidate_root,
        new_inventory,
        active,
        old_root,
        created_at="later",
    )

    assert list(candidate["families"]) == ["zurich", "yokohama"]
    assert candidate["families"]["zurich"]["archived"] is False
    assert candidate["families"]["yokohama"]["archived"] is True
    assert "washington" not in candidate["families"]
    validate_candidate_root(candidate_root, candidate)


def test_archived_inventory_mapping_remains_immutable_across_releases(tmp_path):
    _old_site, old_root, old_inventory, first = _release(
        tmp_path, "yokohama", "sha-1"
    )
    new_site = _site(tmp_path, "zurich", "sha-2")
    new_inventory = build_family_inventory(
        new_site, "zurich", "sha-2", FINGERPRINT, created_at="now"
    )
    candidate = assemble_candidate(
        new_site, tmp_path / "candidate", new_inventory, first, old_root
    )
    archived = candidate["families"]["yokohama"]
    for key in ("artifact_id", "prefix", "tree_sha256", "object_count", "total_bytes"):
        assert archived[key] == old_inventory[key]


def test_release_validation_fails_closed_for_conflicts(tmp_path):
    _site_path, _root, _inventory, release = _release(
        tmp_path, "yokohama", "sha"
    )
    for mutation, message in (
        (lambda value: value.update(latest="missing"), "latest family"),
        (
            lambda value: value["families"]["yokohama"].update(archived=True),
            "latest family",
        ),
        (
            lambda value: value["families"]["yokohama"].update(object_count=0),
            "object count",
        ),
    ):
        invalid = copy.deepcopy(release)
        mutation(invalid)
        invalid["release_id"] = release_id_for(invalid)
        invalid["root_prefix"] = f"releases/{invalid['release_id']}/root"
        with pytest.raises(ValueError, match=message):
            validate_release_manifest(invalid)


def test_remote_verification_requires_exact_objects(tmp_path):
    site = _site(tmp_path, "zurich", "sha")
    inventory = build_family_inventory(site, "zurich", "sha", FINGERPRINT)
    objects = [
        {
            "key": f"{inventory['prefix']}/{item['path']}",
            "bytes": item["bytes"],
        }
        for item in inventory["objects"]
    ]
    verify_uploaded_inventory(inventory, objects)
    with pytest.raises(ValueError, match="remote tree verification"):
        verify_uploaded_inventory(inventory, objects[:-1])


def test_recovery_archive_is_deterministic_splittable_and_reconstructs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("a" * 100, encoding="utf-8")
    (source / "b.txt").write_text("b" * 100, encoding="utf-8")
    one = tmp_path / "one.tar.gz"
    two = tmp_path / "two.tar.gz"
    metadata = create_deterministic_archive(source, one)
    create_deterministic_archive(source, two)
    assert one.read_bytes() == two.read_bytes()

    parts = split_archive(one, tmp_path / "parts", part_size=20)
    assert len(parts) > 1
    destination = tmp_path / "restored"
    reconstruct_archive(
        [tmp_path / "parts" / item["name"] for item in parts],
        metadata["sha256"],
        destination,
    )
    assert (destination / "a.txt").read_text() == "a" * 100
    assert (destination / "b.txt").read_text() == "b" * 100


def test_recovery_rejects_corrupted_part(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_text("content", encoding="utf-8")
    archive = tmp_path / "archive.tar.gz"
    metadata = create_deterministic_archive(source, archive)
    archive.write_bytes(archive.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        reconstruct_archive([archive], metadata["sha256"], tmp_path / "out")


def test_root_and_family_recovery_reconstruct_a_valid_host_agnostic_site(tmp_path):
    site, root, _inventory, _release_manifest = _release(
        tmp_path, "yokohama", "sha"
    )
    root_archive = tmp_path / "root.tar.gz"
    family_archive = tmp_path / "family.tar.gz"
    root_metadata = create_deterministic_archive(root, root_archive)
    family_metadata = create_deterministic_archive(
        site / "yokohama", family_archive
    )

    restored = tmp_path / "restored"
    reconstruct_archive([root_archive], root_metadata["sha256"], restored)
    reconstruct_archive(
        [family_archive],
        family_metadata["sha256"],
        restored / "yokohama",
    )

    validate_site(restored)


def test_cleanup_protects_active_rollback_archived_and_grace_objects(tmp_path):
    _old_site, old_root, _old_inventory, old_release = _release(
        tmp_path, "yokohama", "sha-1"
    )
    new_site = _site(tmp_path, "zurich", "sha-2")
    new_inventory = build_family_inventory(
        new_site, "zurich", "sha-2", FINGERPRINT
    )
    active = assemble_candidate(
        new_site, tmp_path / "new-root", new_inventory, old_release, old_root
    )
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    old = now - timedelta(days=30)
    recent = now - timedelta(days=1)
    objects = [
        StoredObject(
            f"{active['families']['zurich']['prefix']}/index.html", 10, old
        ),
        StoredObject(
            f"{active['families']['yokohama']['prefix']}/index.html", 10, old
        ),
        StoredObject(f"releases/{old_release['release_id']}.json", 10, old),
        StoredObject("content/orphan/dead/index.html", 10, old),
        StoredObject("content/orphan/recent/index.html", 10, recent),
        StoredObject("pointers/preview.json", 10, old),
    ]
    plan = plan_cleanup(
        objects,
        active,
        old_release,
        [old_release, active],
        now=now,
    )
    assert [item["key"] for item in plan["delete"]] == [
        "content/orphan/dead/index.html"
    ]
    assert plan["delete_bytes"] == 10
