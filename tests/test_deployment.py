from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from support import (
    FINGERPRINT,
    production_site as _site,
    recovery_archive as _recovery_archive,
    release as _release,
    write_json as _write_json,
)

from sndocs.artifacts import validate_site
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


def test_inventory_derives_the_recovery_prefix_and_validates_the_archive(tmp_path):
    site = _site(tmp_path, "zurich", "sha")

    inventory = build_family_inventory(
        site,
        "zurich",
        "sha",
        FINGERPRINT,
        created_at="now",
        recovery_archive=_recovery_archive("zurich"),
    )

    artifact_id = family_artifact_id("zurich", "sha", FINGERPRINT)
    assert inventory["recovery"]["prefix"] == (
        f"recovery/families/zurich/{artifact_id}"
    )
    assert inventory["recovery"]["archive"]["name"] == "sndocs-zurich.tar.gz"

    relocated = copy.deepcopy(inventory)
    relocated["recovery"]["prefix"] = "recovery/families/zurich/elsewhere"
    with pytest.raises(ValueError, match="recovery prefix is invalid"):
        validate_family_inventory(relocated)

    unchecksummed = copy.deepcopy(inventory)
    unchecksummed["recovery"]["archive"]["parts"][0]["sha256"] = "short"
    with pytest.raises(ValueError, match="invalid recovery checksum"):
        validate_family_inventory(unchecksummed)

    partless = copy.deepcopy(inventory)
    del partless["recovery"]["archive"]["parts"]
    with pytest.raises(ValueError, match="no parts"):
        validate_family_inventory(partless)


def test_family_inventory_sorts_prefix_collisions_by_serialized_path(tmp_path):
    site = _site(tmp_path, "zurich", "sha")
    family_root = site / "zurich"
    for directory in ("topic", "topic-expanded"):
        page = family_root / directory / "index.html"
        page.parent.mkdir()
        page.write_text(directory, encoding="utf-8")

    first = build_family_inventory(
        site, "zurich", "sha", FINGERPRINT, created_at="now"
    )
    second = build_family_inventory(
        site, "zurich", "sha", FINGERPRINT, created_at="later"
    )
    paths = [entry["path"] for entry in first["objects"]]

    assert paths == sorted(paths)
    assert paths.index("topic-expanded/index.html") < paths.index("topic/index.html")
    assert first["tree_sha256"] == second["tree_sha256"]


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


def test_candidate_assembly_requires_both_active_release_and_active_root(tmp_path):
    _old_site, old_root, _old_inventory, active = _release(
        tmp_path, "yokohama", "sha-1"
    )
    new_site = _site(tmp_path, "zurich", "sha-2")
    new_inventory = build_family_inventory(
        new_site, "zurich", "sha-2", FINGERPRINT, created_at="now"
    )

    with pytest.raises(ValueError, match="active root metadata is required"):
        assemble_candidate(
            new_site, tmp_path / "candidate-a", new_inventory, active, None
        )
    with pytest.raises(ValueError, match="requires the active release manifest"):
        assemble_candidate(
            new_site, tmp_path / "candidate-b", new_inventory, None, old_root
        )


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


def _cleanup_fixture(tmp_path: Path, *, with_recovery: bool):
    _old_site, old_root, _old_inventory, old_release = _release(
        tmp_path, "yokohama", "sha-1", with_recovery=with_recovery
    )
    new_site = _site(tmp_path, "zurich", "sha-2")
    new_inventory = build_family_inventory(
        new_site,
        "zurich",
        "sha-2",
        FINGERPRINT,
        recovery_archive=_recovery_archive("zurich") if with_recovery else None,
    )
    active = assemble_candidate(
        new_site, tmp_path / "new-root", new_inventory, old_release, old_root
    )
    return old_release, active


def test_cleanup_protects_active_rollback_archived_and_grace_objects(tmp_path):
    old_release, active = _cleanup_fixture(tmp_path, with_recovery=True)
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
        StoredObject(
            f"{active['families']['zurich']['recovery']['prefix']}/"
            "sndocs-zurich.tar.gz",
            10,
            old,
        ),
        StoredObject(
            f"{active['families']['yokohama']['recovery']['prefix']}/"
            "sndocs-yokohama.tar.gz",
            10,
            old,
        ),
        StoredObject("content/orphan/dead/index.html", 10, old),
        StoredObject("content/orphan/recent/index.html", 10, recent),
        StoredObject("pointers/preview.json", 10, old),
        StoredObject("pointers/production.json", 10, old),
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


def test_cleanup_refuses_to_plan_without_recovery_protection(tmp_path):
    old_release, active = _cleanup_fixture(tmp_path, with_recovery=False)
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    old = now - timedelta(days=30)
    objects = [StoredObject("content/orphan/dead/index.html", 10, old)]

    with pytest.raises(ValueError, match="cannot protect recovery assets"):
        plan_cleanup(objects, active, old_release, [old_release, active], now=now)

    permitted = plan_cleanup(
        objects,
        active,
        old_release,
        [old_release, active],
        now=now,
        require_recovery=False,
    )
    assert [item["key"] for item in permitted["delete"]] == [
        "content/orphan/dead/index.html"
    ]
