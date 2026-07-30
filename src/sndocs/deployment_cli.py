from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .deployment import (
    DEFAULT_PART_SIZE,
    StoredObject,
    assemble_candidate,
    build_family_inventory,
    calculate_pipeline_fingerprint,
    create_deterministic_archive,
    plan_cleanup,
    plan_latest_release,
    reconstruct_archive,
    sha256_file,
    split_archive,
    validate_candidate_root,
    validate_release_manifest,
    verify_uploaded_inventory,
    verify_uploaded_tree,
)


def _read(path: Path | None) -> dict | None:
    if path is None:
        return None
    if not path.exists():
        raise ValueError(f"required input is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m sndocs.deployment_cli",
        description="Internal Cloudflare release automation for sndocs.com",
    )
    commands = result.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan")
    plan.add_argument("--config", type=Path, default=Path("pipeline.toml"))
    plan.add_argument("--discovery", type=Path, required=True)
    plan_active = plan.add_mutually_exclusive_group(required=True)
    plan_active.add_argument("--active-release", type=Path)
    plan_active.add_argument(
        "--no-active-release",
        action="store_true",
        help="plan an initial release; there is no live release to retain families from",
    )
    plan.add_argument("--output", type=Path, required=True)

    inventory = commands.add_parser("inventory")
    inventory.add_argument("--site", type=Path, required=True)
    inventory.add_argument("--family", required=True)
    inventory.add_argument("--source-sha", required=True)
    inventory.add_argument("--pipeline-fingerprint", required=True)
    inventory.add_argument(
        "--recovery-archive",
        type=Path,
        help="recovery archive metadata written by the package subcommand",
    )
    inventory.add_argument("--output", type=Path, required=True)

    assemble = commands.add_parser("assemble")
    assemble.add_argument("--site", type=Path, required=True)
    assemble.add_argument("--inventory", type=Path, required=True)
    assemble_active = assemble.add_mutually_exclusive_group(required=True)
    assemble_active.add_argument("--active-release", type=Path)
    assemble_active.add_argument(
        "--no-active-release",
        action="store_true",
        help="assemble an initial release; no archived families are retained",
    )
    assemble.add_argument("--active-root", type=Path)
    assemble.add_argument("--output-root", type=Path, required=True)
    assemble.add_argument("--output-manifest", type=Path, required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--root", type=Path)

    verify = commands.add_parser("verify-family-upload")
    verify.add_argument("--inventory", type=Path, required=True)
    verify.add_argument("--remote-list", type=Path, required=True)

    verify_tree = commands.add_parser("verify-tree-upload")
    verify_tree.add_argument("--inventory", type=Path, required=True)
    verify_tree.add_argument("--prefix", required=True)
    verify_tree.add_argument("--remote-list", type=Path, required=True)

    package = commands.add_parser("package")
    package.add_argument("--source", type=Path, required=True)
    package.add_argument("--archive", type=Path, required=True)
    package.add_argument("--parts-dir", type=Path, required=True)
    package.add_argument("--metadata", type=Path, required=True)
    package.add_argument("--part-size", type=int, default=DEFAULT_PART_SIZE)

    reconstruct = commands.add_parser("reconstruct")
    reconstruct.add_argument("--metadata", type=Path, required=True)
    reconstruct.add_argument("--assets", type=Path, required=True)
    reconstruct.add_argument("--destination", type=Path, required=True)

    cleanup = commands.add_parser("cleanup-plan")
    cleanup.add_argument("--objects", type=Path, required=True)
    cleanup.add_argument("--active-release", type=Path, required=True)
    cleanup.add_argument("--rollback-release", type=Path)
    cleanup.add_argument("--public-release", type=Path, action="append", default=[])
    cleanup.add_argument("--output", type=Path, required=True)

    batches = commands.add_parser("cleanup-batches")
    batches.add_argument("--plan", type=Path, required=True)
    batches.add_argument("--destination", type=Path, required=True)
    return result


def _run(args: argparse.Namespace) -> dict:
    if args.command == "plan":
        discovery = _read(args.discovery)
        assert discovery is not None
        fingerprint = calculate_pipeline_fingerprint(args.config)
        result = plan_latest_release(
            discovery, fingerprint, _read(args.active_release)
        )
        _write(args.output, result)
        return result

    if args.command == "inventory":
        result = build_family_inventory(
            args.site,
            args.family,
            args.source_sha,
            args.pipeline_fingerprint,
            recovery_archive=_read(args.recovery_archive),
        )
        _write(args.output, result)
        return result

    if args.command == "assemble":
        inventory = _read(args.inventory)
        assert inventory is not None
        result = assemble_candidate(
            args.site,
            args.output_root,
            inventory,
            _read(args.active_release),
            args.active_root,
        )
        _write(args.output_manifest, result)
        return result

    if args.command == "validate":
        manifest = _read(args.manifest)
        assert manifest is not None
        validate_release_manifest(manifest)
        if args.root:
            validate_candidate_root(args.root, manifest)
        return {"valid": True, "release_id": manifest["release_id"]}

    if args.command == "verify-family-upload":
        inventory = _read(args.inventory)
        remote = _read(args.remote_list)
        assert inventory is not None and remote is not None
        objects = [
            {"key": item["Key"], "bytes": item["Size"]}
            for item in remote.get("Contents", [])
        ]
        verify_uploaded_inventory(inventory, objects)
        return {
            "valid": True,
            "object_count": inventory["object_count"],
            "total_bytes": inventory["total_bytes"],
        }

    if args.command == "verify-tree-upload":
        inventory = _read(args.inventory)
        remote = _read(args.remote_list)
        assert inventory is not None and remote is not None
        objects = [
            {"key": item["Key"], "bytes": item["Size"]}
            for item in remote.get("Contents", [])
        ]
        verify_uploaded_tree(args.prefix, inventory, objects)
        return {
            "valid": True,
            "object_count": inventory["object_count"],
            "total_bytes": inventory["total_bytes"],
        }

    if args.command == "package":
        archive = create_deterministic_archive(args.source, args.archive)
        parts = split_archive(
            args.archive, args.parts_dir, part_size=args.part_size
        )
        if len(parts) > 1:
            args.archive.unlink()
        result = {**archive, "parts": parts}
        _write(args.metadata, result)
        return result

    if args.command == "reconstruct":
        metadata = _read(args.metadata)
        assert metadata is not None
        parts = [args.assets / item["name"] for item in metadata["parts"]]
        for path, expected in zip(parts, metadata["parts"], strict=True):
            actual = sha256_file(path)
            if actual != expected["sha256"]:
                raise ValueError(f"recovery part checksum mismatch: {path.name}")
        reconstruct_archive(parts, metadata["sha256"], args.destination)
        return {"reconstructed": str(args.destination), "files": len(list(args.destination.rglob("*")))}

    if args.command == "cleanup-plan":
        raw_objects = _read(args.objects)
        active = _read(args.active_release)
        assert raw_objects is not None and active is not None
        objects = [
            StoredObject(
                key=item["Key"],
                bytes=item["Size"],
                last_modified=datetime.fromisoformat(
                    item["LastModified"].replace("Z", "+00:00")
                ),
            )
            for item in raw_objects.get("Contents", [])
        ]
        rollback = _read(args.rollback_release)
        public = [_read(path) for path in args.public_release]
        result = plan_cleanup(
            objects,
            active,
            rollback,
            [item for item in public if item is not None],
        )
        _write(args.output, result)
        return result

    if args.command == "cleanup-batches":
        plan = _read(args.plan)
        assert plan is not None
        if plan.get("plan_sha256") is None:
            raise ValueError("cleanup plan has no digest")
        args.destination.mkdir(parents=True, exist_ok=True)
        rows = plan.get("delete", [])
        written = []
        for index in range(0, len(rows), 1000):
            path = args.destination / f"batch-{index // 1000 + 1:04d}.json"
            _write(
                path,
                {
                    "Objects": [
                        {"Key": item["key"]} for item in rows[index : index + 1000]
                    ],
                    "Quiet": False,
                },
            )
            written.append(str(path))
        return {
            "plan_sha256": plan["plan_sha256"],
            "batches": written,
            "delete_count": len(rows),
        }

    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = _run(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"deployment error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
