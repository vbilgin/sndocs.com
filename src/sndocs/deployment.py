from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from .builder import LINK_REPORT_NAME, MANIFEST_NAME, pipeline_fingerprint
from .config import load_settings

RELEASE_SCHEMA_VERSION = 1
FAMILY_INVENTORY_SCHEMA_VERSION = 1
POINTER_SCHEMA_VERSION = 1
ROOT_FILES = (
    "index.html",
    "versions.json",
    MANIFEST_NAME,
    LINK_REPORT_NAME,
    "SERVICENOW-LICENSE.txt",
)
FAMILY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_PART_SIZE = 1_900_000_000


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256_bytes(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _validate_family(family: str) -> None:
    if not FAMILY_RE.fullmatch(family):
        raise ValueError(f"invalid release family: {family!r}")


def family_artifact_id(
    family: str, source_sha: str, pipeline_fingerprint_value: str
) -> str:
    _validate_family(family)
    if not source_sha:
        raise ValueError("source SHA must not be empty")
    if not SHA256_RE.fullmatch(pipeline_fingerprint_value):
        raise ValueError("pipeline fingerprint must be a lowercase SHA-256 digest")
    return _sha256_bytes(
        {
            "family": family,
            "pipeline_fingerprint": pipeline_fingerprint_value,
            "source_sha": source_sha,
        }
    )


def calculate_pipeline_fingerprint(config: Path) -> str:
    return pipeline_fingerprint(load_settings(config.resolve()))


def plan_latest_release(
    discovery: dict, pipeline_fingerprint_value: str, active_release: dict | None
) -> dict:
    latest = discovery.get("latest")
    shas = discovery.get("shas", {})
    if not isinstance(latest, str) or latest not in shas:
        raise ValueError("discovery must identify latest and its source SHA")
    _validate_family(latest)
    source_sha = shas[latest]
    artifact_id = family_artifact_id(latest, source_sha, pipeline_fingerprint_value)

    if active_release is None:
        action = "initial"
        reason = "no active public release"
    else:
        validate_release_manifest(active_release)
        current_latest = active_release["latest"]
        current = active_release["families"][current_latest]
        if current_latest != latest:
            action = "new-latest"
            reason = f"latest family changed from {current_latest} to {latest}"
        elif (
            current["source_sha"] == source_sha
            and current["pipeline_fingerprint"] == pipeline_fingerprint_value
        ):
            action = "none"
            reason = "latest family, source SHA, and pipeline fingerprint are unchanged"
        else:
            action = "rebuild"
            changed = []
            if current["source_sha"] != source_sha:
                changed.append("source SHA")
            if current["pipeline_fingerprint"] != pipeline_fingerprint_value:
                changed.append("pipeline fingerprint")
            reason = f"latest {' and '.join(changed)} changed"

    return {
        "action": action,
        "changed": action != "none",
        "reason": reason,
        "latest": latest,
        "source_sha": source_sha,
        "pipeline_fingerprint": pipeline_fingerprint_value,
        "artifact_id": artifact_id,
        "content_prefix": f"content/{latest}/{artifact_id}",
    }


def _pointer(release_id: str) -> dict:
    if not SHA256_RE.fullmatch(release_id or ""):
        raise ValueError(f"release pointer needs a release digest: {release_id!r}")
    return {"schema_version": POINTER_SCHEMA_VERSION, "release_id": release_id}


def preview_pointer(release_id: str) -> dict:
    """The mutable candidate pointer that only the preview Worker reads."""
    return _pointer(release_id)


def production_pointer(release_id: str) -> dict:
    """The record of what is live. The Worker must never read this.

    Production pins its release through a versioned Worker variable; this
    object exists so a local operator can answer "what is live?" without
    guessing from object listings.
    """
    return _pointer(release_id)


def build_reconstruction(release: dict, root_recovery: dict) -> dict:
    """Describe how to rebuild the published site from recovery assets."""
    validate_release_manifest(release)
    latest = release["latest"]
    families: dict[str, dict | None] = {}
    without_recovery = []
    for family, record in release["families"].items():
        archive = record.get("recovery", {}).get("archive")
        if archive is None:
            if family == latest:
                raise ValueError(
                    f"latest family {family} has no recovery archive; "
                    "recovery assets must exist before a release is published"
                )
            without_recovery.append(family)
        families[family] = archive
    return {
        "schema_version": 1,
        "release_id": release["release_id"],
        "latest": latest,
        "root": root_recovery,
        "families": families,
        "families_without_recovery": sorted(without_recovery),
    }


def recovery_checksum_manifest(paths: Iterable[Path]) -> str:
    """Return coreutils-format checksums, ordered by name rather than by glob."""
    rows = sorted((path.name, sha256_file(path)) for path in paths)
    names = [name for name, _ in rows]
    if len(names) != len(set(names)):
        raise ValueError("recovery assets contain duplicate names")
    return "".join(f"{digest}  {name}\n" for name, digest in rows)


def _tree_entries(root: Path) -> list[dict]:
    entries = []
    for path in (candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
            raise ValueError(f"unsafe inventory path: {relative}")
        digest = sha256_file(path)
        entries.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest})
    entries.sort(key=lambda entry: entry["path"])
    return entries


def inventory_tree(root: Path) -> dict:
    if not root.is_dir():
        raise ValueError(f"inventory root does not exist: {root}")
    entries = _tree_entries(root)
    if not entries:
        raise ValueError(f"inventory root contains no files: {root}")
    return {
        "object_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "tree_sha256": _sha256_bytes(entries),
        "objects": entries,
    }


def recovery_prefix_for(family: str, artifact_id: str) -> str:
    return f"recovery/families/{family}/{artifact_id}"


def build_family_inventory(
    site: Path,
    family: str,
    source_sha: str,
    pipeline_fingerprint_value: str,
    *,
    created_at: str | None = None,
    recovery_archive: dict | None = None,
) -> dict:
    _validate_family(family)
    family_root = site / family
    site_manifest = _read_json(site / MANIFEST_NAME)
    if site_manifest.get("build_profile") != "production":
        raise ValueError("only production family output can be published")
    if site_manifest.get("latest") != family:
        raise ValueError("single-family build manifest does not identify the requested family")
    if set(site_manifest.get("families", {})) != {family}:
        raise ValueError("deployment builds must contain exactly the latest family")
    record = site_manifest["families"][family]
    if record.get("source_sha") != source_sha:
        raise ValueError("built family source SHA disagrees with deployment plan")
    if site_manifest.get("pipeline_fingerprint") != pipeline_fingerprint_value:
        raise ValueError("built family pipeline fingerprint disagrees with deployment plan")
    if record.get("archived"):
        raise ValueError("newly built latest family cannot be archived")
    if not (family_root / "index.html").is_file():
        raise ValueError(f"family {family} has no index.html")
    tree = inventory_tree(family_root)
    artifact_id = family_artifact_id(family, source_sha, pipeline_fingerprint_value)
    inventory = {
        "schema_version": FAMILY_INVENTORY_SCHEMA_VERSION,
        "family": family,
        "artifact_id": artifact_id,
        "prefix": f"content/{family}/{artifact_id}",
        "source_sha": source_sha,
        "pipeline_fingerprint": pipeline_fingerprint_value,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "archived": False,
        "object_count": tree["object_count"],
        "total_bytes": tree["total_bytes"],
        "tree_sha256": tree["tree_sha256"],
        "objects": tree["objects"],
        "link_counts": record["link_counts"],
    }
    if recovery_archive is not None:
        # The prefix is derived here rather than supplied, so a caller cannot
        # record recovery assets under a location cleanup will not protect.
        inventory["recovery"] = {
            "prefix": recovery_prefix_for(family, artifact_id),
            "archive": recovery_archive,
        }
    validate_family_inventory(inventory)
    return inventory


def validate_family_inventory(inventory: dict) -> None:
    required = {
        "schema_version",
        "family",
        "artifact_id",
        "prefix",
        "source_sha",
        "pipeline_fingerprint",
        "created_at",
        "archived",
        "object_count",
        "total_bytes",
        "tree_sha256",
        "objects",
        "link_counts",
    }
    missing = required - inventory.keys()
    if missing:
        raise ValueError(f"family inventory is missing: {', '.join(sorted(missing))}")
    if inventory["schema_version"] != FAMILY_INVENTORY_SCHEMA_VERSION:
        raise ValueError("unsupported family inventory schema")
    family = inventory["family"]
    _validate_family(family)
    expected_id = family_artifact_id(
        family, inventory["source_sha"], inventory["pipeline_fingerprint"]
    )
    if inventory["artifact_id"] != expected_id:
        raise ValueError("family artifact ID is not deterministic")
    if inventory["prefix"] != f"content/{family}/{expected_id}":
        raise ValueError("family inventory prefix is invalid")
    objects = inventory["objects"]
    if not isinstance(objects, list) or not objects:
        raise ValueError("family inventory must contain objects")
    paths = []
    for entry in objects:
        path = entry.get("path", "")
        parsed = PurePosixPath(path)
        if not path or parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError(f"unsafe family inventory path: {path!r}")
        if not SHA256_RE.fullmatch(entry.get("sha256", "")):
            raise ValueError(f"invalid checksum for family object: {path}")
        if not isinstance(entry.get("bytes"), int) or entry["bytes"] < 0:
            raise ValueError(f"invalid byte count for family object: {path}")
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise ValueError("family inventory contains duplicate paths")
    canonical = sorted(objects, key=lambda item: item["path"])
    if objects != canonical:
        raise ValueError("family inventory objects must be path-sorted")
    if inventory["object_count"] != len(objects):
        raise ValueError("family inventory object count is incorrect")
    if inventory["total_bytes"] != sum(item["bytes"] for item in objects):
        raise ValueError("family inventory byte count is incorrect")
    if inventory["tree_sha256"] != _sha256_bytes(objects):
        raise ValueError("family inventory tree digest is incorrect")
    if "recovery" in inventory:
        _validate_recovery(family, expected_id, inventory["recovery"])


def _validate_recovery(family: str, artifact_id: str, recovery: object) -> None:
    if not isinstance(recovery, dict):
        raise ValueError(f"family {family} recovery metadata must be an object")
    expected_prefix = recovery_prefix_for(family, artifact_id)
    if recovery.get("prefix") != expected_prefix:
        raise ValueError(f"family {family} recovery prefix is invalid")
    archive = recovery.get("archive")
    if not isinstance(archive, dict):
        raise ValueError(f"family {family} recovery archive metadata is missing")
    parts = archive.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError(f"family {family} recovery archive has no parts")
    for entry in (archive, *parts):
        name = entry.get("name", "")
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"unsafe recovery asset name for {family}: {name!r}")
        if not SHA256_RE.fullmatch(entry.get("sha256", "")):
            raise ValueError(f"invalid recovery checksum for {family}: {name}")
        if not isinstance(entry.get("bytes"), int) or entry["bytes"] < 0:
            raise ValueError(f"invalid recovery byte count for {family}: {name}")


def _family_release_record(inventory: dict, *, archived: bool) -> dict:
    validate_family_inventory(inventory)
    record = {
        key: value
        for key, value in inventory.items()
        if key != "objects"
    }
    record["archived"] = archived
    return record


def _validate_family_release_record(family: str, record: dict) -> None:
    required = {
        "schema_version",
        "family",
        "artifact_id",
        "prefix",
        "source_sha",
        "pipeline_fingerprint",
        "created_at",
        "archived",
        "object_count",
        "total_bytes",
        "tree_sha256",
        "link_counts",
    }
    missing = required - record.keys()
    if missing:
        raise ValueError(
            f"release family record {family} is missing: {', '.join(sorted(missing))}"
        )
    if record["schema_version"] != FAMILY_INVENTORY_SCHEMA_VERSION:
        raise ValueError("unsupported family inventory schema")
    if record["family"] != family:
        raise ValueError(f"release family record disagrees with key: {family}")
    _validate_family(family)
    expected_id = family_artifact_id(
        family, record["source_sha"], record["pipeline_fingerprint"]
    )
    if record["artifact_id"] != expected_id:
        raise ValueError(f"release family artifact ID is invalid: {family}")
    if record["prefix"] != f"content/{family}/{expected_id}":
        raise ValueError(f"release family prefix is invalid: {family}")
    if not isinstance(record["object_count"], int) or record["object_count"] <= 0:
        raise ValueError(f"release family object count is invalid: {family}")
    if not isinstance(record["total_bytes"], int) or record["total_bytes"] < 0:
        raise ValueError(f"release family byte count is invalid: {family}")
    if not SHA256_RE.fullmatch(record["tree_sha256"]):
        raise ValueError(f"release family tree digest is invalid: {family}")
    if "recovery" in record:
        _validate_recovery(family, expected_id, record["recovery"])


def _release_identity_payload(manifest: dict) -> dict:
    return {
        "schema_version": manifest["schema_version"],
        "created_at": manifest["created_at"],
        "latest": manifest["latest"],
        "pipeline_fingerprint": manifest["pipeline_fingerprint"],
        "families": manifest["families"],
        "root": manifest["root"],
    }


def release_id_for(manifest: dict) -> str:
    return _sha256_bytes(_release_identity_payload(manifest))


def validate_release_manifest(manifest: dict) -> None:
    required = {
        "schema_version",
        "release_id",
        "created_at",
        "latest",
        "pipeline_fingerprint",
        "root_prefix",
        "root",
        "families",
    }
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"release manifest is missing: {', '.join(sorted(missing))}")
    if manifest["schema_version"] != RELEASE_SCHEMA_VERSION:
        raise ValueError("unsupported release manifest schema")
    if not SHA256_RE.fullmatch(manifest["pipeline_fingerprint"]):
        raise ValueError("release pipeline fingerprint is invalid")
    expected_id = release_id_for(manifest)
    if manifest["release_id"] != expected_id:
        raise ValueError("release ID does not match the canonical manifest")
    if manifest["root_prefix"] != f"releases/{expected_id}/root":
        raise ValueError("release root prefix is invalid")
    families = manifest["families"]
    latest = manifest["latest"]
    if not isinstance(families, dict) or latest not in families:
        raise ValueError("release latest family is absent")
    for family, record in families.items():
        _validate_family_release_record(family, record)
        if family == latest and record["archived"]:
            raise ValueError("latest family cannot be archived")
        if family != latest and not record["archived"]:
            raise ValueError(f"non-latest family must be archived: {family}")
    root = manifest["root"]
    objects = root.get("objects", [])
    if not isinstance(objects, list):
        raise ValueError("release root objects are invalid")
    if [item.get("path") for item in objects] != sorted(ROOT_FILES):
        raise ValueError("release root must contain the exact public root files")
    for item in objects:
        if (
            not isinstance(item.get("bytes"), int)
            or item["bytes"] < 0
            or not SHA256_RE.fullmatch(item.get("sha256", ""))
        ):
            raise ValueError(f"release root object is invalid: {item.get('path')}")
    if root.get("object_count") != len(objects):
        raise ValueError("release root object count is incorrect")
    if root.get("total_bytes") != sum(
        item["bytes"] for item in objects
    ):
        raise ValueError("release root byte count is incorrect")
    if root.get("tree_sha256") != _sha256_bytes(objects):
        raise ValueError("release root tree digest is incorrect")


def _retained_families(
    active_release: dict | None, latest_inventory: dict
) -> dict[str, dict]:
    family = latest_inventory["family"]
    retained = {}
    if active_release:
        validate_release_manifest(active_release)
        for name, record in active_release["families"].items():
            if name == family:
                continue
            retained[name] = {**record, "archived": True}
    retained[family] = _family_release_record(latest_inventory, archived=False)
    return {
        family: retained[family],
        **{name: value for name, value in retained.items() if name != family},
    }


def _active_root_data(active_root: Path | None) -> tuple[dict, dict, dict]:
    if active_root is None:
        return {}, {}, {}
    manifest = _read_json(active_root / MANIFEST_NAME)
    versions = _read_json(active_root / "versions.json")
    links = _read_json(active_root / LINK_REPORT_NAME)
    return manifest, versions, links


def assemble_candidate(
    site: Path,
    output: Path,
    latest_inventory: dict,
    active_release: dict | None = None,
    active_root: Path | None = None,
    *,
    created_at: str | None = None,
) -> dict:
    validate_family_inventory(latest_inventory)
    latest = latest_inventory["family"]
    built_manifest = _read_json(site / MANIFEST_NAME)
    built_links = _read_json(site / LINK_REPORT_NAME)
    if set(built_manifest["families"]) != {latest}:
        raise ValueError("candidate assembly requires a single-family production build")
    if active_release is not None and active_root is None:
        raise ValueError("active root metadata is required when retaining archived families")
    if active_root is not None and active_release is None:
        raise ValueError("active root metadata requires the active release manifest")
    active_manifest, active_versions, active_links = _active_root_data(active_root)
    families = _retained_families(active_release, latest_inventory)

    if output.exists():
        raise ValueError(f"candidate root already exists: {output}")
    output.mkdir(parents=True)
    for name in ("index.html", "SERVICENOW-LICENSE.txt"):
        shutil.copy2(site / name, output / name)

    active_version_map = {
        item["family"]: item for item in active_versions.get("versions", [])
    }
    versions = {
        "latest": latest,
        "versions": [
            {
                "family": family,
                "title": active_version_map.get(family, {}).get(
                    "title", family.title()
                ),
                "path": f"/{family}/",
                "archived": record["archived"],
            }
            for family, record in families.items()
        ],
    }
    _write_json(output / "versions.json", versions)

    family_build_records = {}
    family_link_reports = {}
    for family, record in families.items():
        if family == latest:
            build_record = built_manifest["families"][family]
            link_report = built_links["families"][family]
        else:
            if family not in active_manifest.get("families", {}):
                raise ValueError(f"active root manifest is missing retained family {family}")
            if family not in active_links.get("families", {}):
                raise ValueError(f"active link report is missing retained family {family}")
            build_record = active_manifest["families"][family]
            link_report = active_links["families"][family]
        family_build_records[family] = {
            **build_record,
            "source_sha": record["source_sha"],
            "archived": record["archived"],
            "path": f"/{family}/",
            "artifact_id": record["artifact_id"],
            "content_prefix": record["prefix"],
        }
        family_link_reports[family] = link_report

    root_build_manifest = {
        **built_manifest,
        "latest": latest,
        "families": family_build_records,
    }
    _write_json(output / MANIFEST_NAME, root_build_manifest)
    _write_json(
        output / LINK_REPORT_NAME,
        {"schema_version": 2, "families": family_link_reports},
    )

    root_inventory = inventory_tree(output)
    release = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "latest": latest,
        "pipeline_fingerprint": latest_inventory["pipeline_fingerprint"],
        "families": families,
        "root": root_inventory,
    }
    release_id = release_id_for(release)
    release["release_id"] = release_id
    release["root_prefix"] = f"releases/{release_id}/root"
    validate_release_manifest(release)
    validate_candidate_root(output, release)
    return release


def validate_candidate_root(root: Path, release: dict) -> None:
    validate_release_manifest(release)
    actual = inventory_tree(root)
    if actual != release["root"]:
        raise ValueError("candidate root objects do not match the release manifest")
    manifest = _read_json(root / MANIFEST_NAME)
    versions = _read_json(root / "versions.json")
    links = _read_json(root / LINK_REPORT_NAME)
    expected = set(release["families"])
    if manifest.get("latest") != release["latest"] or versions.get("latest") != release["latest"]:
        raise ValueError("candidate root metadata has conflicting latest families")
    if set(manifest.get("families", {})) != expected:
        raise ValueError("candidate build manifest family set is inconsistent")
    if {item.get("family") for item in versions.get("versions", [])} != expected:
        raise ValueError("candidate versions family set is inconsistent")
    if set(links.get("families", {})) != expected:
        raise ValueError("candidate link report family set is inconsistent")
    for family, record in release["families"].items():
        root_record = manifest["families"][family]
        if root_record.get("source_sha") != record["source_sha"]:
            raise ValueError(f"candidate source SHA mismatch for {family}")
        if root_record.get("archived") != record["archived"]:
            raise ValueError(f"candidate archive-state mismatch for {family}")
        if root_record.get("artifact_id") != record["artifact_id"]:
            raise ValueError(f"candidate artifact mismatch for {family}")


def verify_uploaded_inventory(inventory: dict, remote_objects: list[dict]) -> None:
    validate_family_inventory(inventory)
    verify_uploaded_tree(inventory["prefix"], inventory, remote_objects)


def verify_uploaded_tree(
    prefix: str, inventory: dict, remote_objects: list[dict]
) -> None:
    if inventory.get("object_count") != len(inventory.get("objects", [])):
        raise ValueError("upload inventory object count is incorrect")
    expected = {
        f"{prefix}/{item['path']}": item["bytes"]
        for item in inventory["objects"]
    }
    actual = {item["key"]: item["bytes"] for item in remote_objects}
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        unexpected = sorted(actual.keys() - expected.keys())
        mismatched = sorted(
            key for key in expected.keys() & actual.keys() if expected[key] != actual[key]
        )
        details = []
        if missing:
            details.append(f"missing {len(missing)}")
        if unexpected:
            details.append(f"unexpected {len(unexpected)}")
        if mismatched:
            details.append(f"size mismatch {len(mismatched)}")
        raise ValueError(f"remote tree verification failed ({', '.join(details)})")


def _archive_files(source: Path) -> list[Path]:
    return sorted(path for path in source.rglob("*") if path.is_file())


def create_deterministic_archive(source: Path, destination: Path) -> dict:
    if not source.is_dir():
        raise ValueError(f"archive source does not exist: {source}")
    files = _archive_files(source)
    if not files:
        raise ValueError(f"archive source contains no files: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
            ) as archive:
                for path in files:
                    info = archive.gettarinfo(
                        str(path), arcname=path.relative_to(source).as_posix()
                    )
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    info.mode = 0o644
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
    return {
        "name": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }


def split_archive(
    archive: Path, destination: Path, *, part_size: int = DEFAULT_PART_SIZE
) -> list[dict]:
    if part_size <= 0:
        raise ValueError("archive part size must be positive")
    destination.mkdir(parents=True, exist_ok=True)
    total_size = archive.stat().st_size
    if total_size <= part_size:
        target = destination / archive.name
        if archive.resolve() != target.resolve():
            shutil.copy2(archive, target)
        return [
            {
                "name": target.name,
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
            }
        ]
    parts = []
    with archive.open("rb") as source:
        index = 1
        while source.tell() < total_size:
            part = destination / f"{archive.name}.part-{index:04d}"
            remaining = min(part_size, total_size - source.tell())
            digest = hashlib.sha256()
            written = 0
            with part.open("wb") as output:
                while remaining:
                    chunk = source.read(min(8 * 1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("recovery archive ended while splitting")
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            parts.append(
                {
                    "name": part.name,
                    "bytes": written,
                    "sha256": digest.hexdigest(),
                }
            )
            index += 1
    return parts


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not member.isfile():
            raise ValueError(f"unsafe or unsupported recovery member: {member.name}")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"recovery member has no data: {member.name}")
        target = destination.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def reconstruct_archive(parts: Iterable[Path], expected_sha256: str, destination: Path) -> None:
    ordered = list(parts)
    if not ordered:
        raise ValueError("no recovery archive parts were supplied")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"recovery destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    combined = destination.parent / f".{destination.name}-recovery.tar.gz"
    digest = hashlib.sha256()
    with combined.open("wb") as output:
        for part in ordered:
            with part.open("rb") as stream:
                while chunk := stream.read(8 * 1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
    try:
        if digest.hexdigest() != expected_sha256:
            raise ValueError("recovery archive checksum mismatch")
        with tarfile.open(combined, "r:gz") as archive:
            _safe_extract(archive, destination)
    finally:
        combined.unlink(missing_ok=True)


@dataclass(frozen=True)
class StoredObject:
    key: str
    bytes: int
    last_modified: datetime


def _require_recovery_metadata(
    releases: list[dict], public_releases: list[dict]
) -> None:
    """Refuse to plan a cleanup that cannot protect its recovery assets.

    Recovery protection is derived from ``recovery.prefix`` on each family
    record. A record without it is not protected, so planning would quietly
    select recovery assets for deletion. Fail closed instead.
    """
    unprotected = set()
    for release in releases:
        for record in release["families"].values():
            if not record.get("recovery", {}).get("prefix"):
                unprotected.add(record["family"])
    for release in public_releases:
        for record in release["families"].values():
            if record["archived"] and not record.get("recovery", {}).get("prefix"):
                unprotected.add(record["family"])
    if unprotected:
        raise ValueError(
            "cleanup cannot protect recovery assets for: "
            + ", ".join(sorted(unprotected))
            + "; pass require_recovery=False only for a release that was "
            "published before recovery metadata was recorded"
        )


def plan_cleanup(
    objects: Iterable[StoredObject],
    active_release: dict,
    rollback_release: dict | None,
    public_releases: Iterable[dict],
    *,
    now: datetime | None = None,
    grace_period: timedelta = timedelta(days=14),
    require_recovery: bool = True,
) -> dict:
    validate_release_manifest(active_release)
    releases = [active_release]
    if rollback_release:
        validate_release_manifest(rollback_release)
        releases.append(rollback_release)
    all_public = list(public_releases)
    for release in all_public:
        validate_release_manifest(release)

    if require_recovery:
        _require_recovery_metadata(releases, all_public)

    protected_prefixes = {
        f"releases/{release['release_id']}/"
        for release in releases
    }
    protected_prefixes.update(
        record["prefix"] + "/"
        for release in releases
        for record in release["families"].values()
    )
    protected_prefixes.update(
        record["prefix"] + "/"
        for release in all_public
        for record in release["families"].values()
        if record["archived"]
    )
    protected_prefixes.update(
        record["recovery"]["prefix"].rstrip("/") + "/"
        for release in releases
        for record in release["families"].values()
        if record.get("recovery", {}).get("prefix")
    )
    protected_prefixes.update(
        record["recovery"]["prefix"].rstrip("/") + "/"
        for release in all_public
        for record in release["families"].values()
        if record["archived"] and record.get("recovery", {}).get("prefix")
    )
    protected_prefixes.update(
        f"recovery/releases/{release['release_id']}/" for release in releases
    )
    protected_prefixes.update(
        f"inventories/{record['family']}/{record['artifact_id']}"
        for release in releases
        for record in release["families"].values()
    )
    protected_keys = {
        f"releases/{release['release_id']}.json" for release in releases
    }
    protected_keys.add("pointers/preview.json")
    protected_keys.add("pointers/production.json")
    cutoff = (now or datetime.now(timezone.utc)) - grace_period
    deletions = []
    retained = []
    for item in sorted(objects, key=lambda value: value.key):
        protected = item.key in protected_keys or any(
            item.key.startswith(prefix) for prefix in protected_prefixes
        )
        in_grace = item.last_modified > cutoff
        if protected or in_grace:
            retained.append(item)
        elif item.key.startswith(
            ("content/", "inventories/", "releases/", "recovery/")
        ):
            deletions.append(item)
        else:
            retained.append(item)
    deletion_rows = [{"key": item.key, "bytes": item.bytes} for item in deletions]
    return {
        "schema_version": 1,
        "cutoff": cutoff.isoformat(),
        "protected_prefixes": sorted(protected_prefixes),
        "delete": deletion_rows,
        "delete_count": len(deletion_rows),
        "delete_bytes": sum(item["bytes"] for item in deletion_rows),
        "retained_count": len(retained),
        "plan_sha256": _sha256_bytes(deletion_rows),
    }
