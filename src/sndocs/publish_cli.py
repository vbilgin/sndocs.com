"""Operator-driven publication for sndocs.com.

This module replaces the retired GitHub Actions publication workflow. It is the
only place that performs irreversible side effects: R2 transfers and Worker
deployments. Release *decisions* stay in the pure ``deployment`` module, and
``deployment_cli`` stays a pure file-in/file-out shim over it.

Run the subcommands in the order documented in ``docs/deployment-runbook.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from .artifacts import validate_site
from .builder import build_site
from .config import load_settings
from .deployment import (
    DEFAULT_PART_SIZE,
    ROOT_FILES,
    StoredObject,
    assemble_candidate,
    build_family_inventory,
    build_reconstruction,
    calculate_pipeline_fingerprint,
    create_deterministic_archive,
    plan_cleanup,
    plan_latest_release,
    preview_pointer,
    production_pointer,
    recovery_checksum_manifest,
    release_id_for,
    split_archive,
    validate_candidate_root,
    validate_release_manifest,
    verify_uploaded_inventory,
    verify_uploaded_tree,
)
from .discovery import discover
from .r2 import R2Client, R2Config, R2Error
from .source import LocalSource

PRODUCTION_POINTER_KEY = "pointers/production.json"
PREVIEW_POINTER_KEY = "pointers/preview.json"
JSON_CONTENT_TYPE = "application/json"


class PublishError(RuntimeError):
    """A publication step refused to continue."""


# -- small helpers ----------------------------------------------------------


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise PublishError(f"required input is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _remote_objects(client: R2Client, prefix: str) -> list[dict]:
    return [
        {"key": item["Key"], "bytes": item["Size"]}
        for item in client.list_objects(prefix)
    ]


def _upload_immutable_tree(
    client: R2Client, local: Path, prefix: str, verify
) -> dict:
    """Upload ``local`` to ``prefix`` unless the prefix already has objects.

    A published prefix is immutable: its name contains a digest of everything
    inside it. If objects are already there, the correct action is to verify,
    never to overwrite. Divergence means a corrupt earlier upload or a digest
    collision, and is reported as its own failure.
    """
    listed = prefix.rstrip("/") + "/"
    existing = _remote_objects(client, listed)
    reused = bool(existing)
    if not reused:
        client.put_tree(local, prefix)
        existing = _remote_objects(client, listed)
    try:
        verify(existing)
    except ValueError as error:
        if reused:
            raise PublishError(
                f"immutable prefix diverges from local build: {prefix} ({error}). "
                "Do not overwrite it; investigate the earlier upload."
            ) from error
        raise PublishError(f"upload verification failed for {prefix}: {error}") from error
    return {"prefix": prefix, "objects": len(existing), "reused": reused}


def _require_clean_workspace(paths: list[Path], clean: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return
    if not clean:
        joined = ", ".join(str(path) for path in existing)
        raise PublishError(
            f"stale working directories from a prior run exist: {joined}; "
            "pass --clean to remove them first"
        )
    for path in existing:
        shutil.rmtree(path)


def _package_recovery(
    source: Path, archive: Path, assets: Path, part_size: int
) -> dict:
    archive_metadata = create_deterministic_archive(source, archive)
    parts = split_archive(archive, assets, part_size=part_size)
    if len(parts) > 1:
        archive.unlink()
    return {**archive_metadata, "parts": parts}


# -- subcommands ------------------------------------------------------------


def resolve_active(args, client: R2Client) -> dict:
    """Answer "what is live?" from the production pointer, or fail closed."""
    pointer_body = client.get_bytes(PRODUCTION_POINTER_KEY)
    if pointer_body is None:
        if not args.allow_bootstrap:
            raise PublishError(
                f"{PRODUCTION_POINTER_KEY} is absent, so the live release is "
                "unknown. Publishing now would drop every archived family from "
                "the release. Pass --allow-bootstrap only for the first release."
            )
        if args.output.exists():
            raise PublishError(
                f"bootstrap requested but {args.output} already exists; remove "
                "the stale manifest so it cannot be reused as the active release"
            )
        return {"state": "bootstrap", "release_id": None}

    release_id = json.loads(pointer_body).get("release_id")
    manifest_body = client.get_bytes(f"releases/{release_id}.json")
    if manifest_body is None:
        raise PublishError(
            f"{PRODUCTION_POINTER_KEY} names release {release_id}, but "
            f"releases/{release_id}.json does not exist"
        )
    manifest = json.loads(manifest_body)
    validate_release_manifest(manifest)
    if manifest["release_id"] != release_id or release_id_for(manifest) != release_id:
        raise PublishError(
            f"release {release_id} does not hash to its own identity; "
            "the manifest in R2 has been altered"
        )

    github_state = "not compared"
    if args.github_manifest:
        if not args.github_manifest.exists():
            raise PublishError(
                f"recovery manifest to compare is missing: {args.github_manifest}"
            )
        github_state = (
            "identical"
            if args.github_manifest.read_bytes() == manifest_body
            else "different"
        )
        if github_state == "different":
            raise PublishError(
                "the GitHub Release copy of the active manifest differs from R2; "
                "resolve the divergence before publishing"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(manifest_body)
    return {
        "state": "active",
        "release_id": release_id,
        "latest": manifest["latest"],
        "families": sorted(manifest["families"]),
        "github_manifest": github_state,
        "output": str(args.output),
    }


def push_family(args, client: R2Client) -> dict:
    """Package, inventory, and immutably upload the freshly built latest family."""
    plan = _read_json(args.plan)
    if not plan.get("changed", False):
        raise PublishError(
            f"deployment plan reports no change ({plan.get('reason')}); "
            "there is nothing to publish"
        )
    family = plan["latest"]
    handoff = args.handoff
    assets = handoff / "recovery" / "assets"

    recovery = _package_recovery(
        args.site / family,
        assets / f"sndocs-{family}.tar.gz",
        assets,
        args.part_size,
    )
    inventory = build_family_inventory(
        args.site,
        family,
        plan["source_sha"],
        plan["pipeline_fingerprint"],
        recovery_archive=recovery,
    )
    if inventory["prefix"] != plan["content_prefix"]:
        raise PublishError(
            "built family prefix disagrees with the deployment plan: "
            f"{inventory['prefix']} != {plan['content_prefix']}"
        )

    uploaded = _upload_immutable_tree(
        client,
        args.site / family,
        inventory["prefix"],
        lambda objects: verify_uploaded_inventory(inventory, objects),
    )
    _write_json(handoff / "family-inventory.json", inventory)
    _write_json(handoff / "family-recovery.json", recovery)
    client.put_bytes(
        f"inventories/{family}/{inventory['artifact_id']}.json",
        (handoff / "family-inventory.json").read_bytes(),
        content_type=JSON_CONTENT_TYPE,
    )
    client.put_tree(assets, inventory["recovery"]["prefix"])
    client.put_bytes(
        f"{inventory['recovery']['prefix']}/metadata.json",
        (handoff / "family-recovery.json").read_bytes(),
        content_type=JSON_CONTENT_TYPE,
    )
    return {
        "family": family,
        "artifact_id": inventory["artifact_id"],
        "object_count": inventory["object_count"],
        "total_bytes": inventory["total_bytes"],
        "recovery_parts": len(recovery["parts"]),
        **uploaded,
    }


def assemble(args, client: R2Client) -> dict:
    """Build the candidate release root, retaining archived families."""
    inventory = _read_json(args.inventory)
    active_release = None
    active_root = None
    if args.active_release:
        active_release = _read_json(args.active_release)
        validate_release_manifest(active_release)
        active_root = args.candidate / "active-root"
        client.get_tree(active_release["root_prefix"], active_root)
        missing = [
            name for name in ROOT_FILES if not (active_root / name).is_file()
        ]
        if missing:
            raise PublishError(
                "active release root is incomplete in R2: " + ", ".join(missing)
            )

    release = assemble_candidate(
        args.site,
        args.candidate / "root",
        inventory,
        active_release,
        active_root,
    )
    _write_json(args.candidate / "release-manifest.json", release)
    return {
        "release_id": release["release_id"],
        "root_prefix": release["root_prefix"],
        "latest": release["latest"],
        "families": {
            family: "archived" if record["archived"] else "current"
            for family, record in release["families"].items()
        },
    }


def push_candidate(args, client: R2Client) -> dict:
    """Upload the candidate root, then the manifest, then the preview pointer."""
    manifest_path = args.candidate / "release-manifest.json"
    release = _read_json(manifest_path)
    validate_release_manifest(release)
    root = args.candidate / "root"
    validate_candidate_root(root, release)
    release_id = release["release_id"]

    uploaded = _upload_immutable_tree(
        client,
        root,
        release["root_prefix"],
        lambda objects: verify_uploaded_tree(
            release["root_prefix"], release["root"], objects
        ),
    )

    assets = args.candidate / "recovery" / "assets"
    root_recovery = _package_recovery(
        root, assets / "sndocs-root.tar.gz", assets, args.part_size
    )
    _write_json(args.candidate / "root-recovery.json", root_recovery)
    client.put_tree(assets, f"recovery/releases/{release_id}")
    client.put_bytes(
        f"recovery/releases/{release_id}/metadata.json",
        (args.candidate / "root-recovery.json").read_bytes(),
        content_type=JSON_CONTENT_TYPE,
    )

    # The manifest is uploaded last: until it exists, the release cannot be
    # resolved, so a partial upload is never servable.
    manifest_bytes = manifest_path.read_bytes()
    key = f"releases/{release_id}.json"
    client.put_bytes(key, manifest_bytes, content_type=JSON_CONTENT_TYPE)
    if client.get_bytes(key) != manifest_bytes:
        raise PublishError(
            f"{key} read back differently than it was uploaded; do not promote "
            "this release"
        )

    client.put_bytes(
        PREVIEW_POINTER_KEY,
        json.dumps(preview_pointer(release_id), indent=2).encode() + b"\n",
        content_type=JSON_CONTENT_TYPE,
        cache_control="no-store",
    )
    return {
        "release_id": release_id,
        "manifest": key,
        "preview_pointer": PREVIEW_POINTER_KEY,
        "recovery_parts": len(root_recovery["parts"]),
        **uploaded,
    }


def stage(args, client: R2Client) -> dict:
    """Run preflight, then discovery through push-candidate, in one command."""
    _run_tool([sys.executable, "-m", "pytest"], cwd=None, description="pytest")
    _run_tool(
        ["npm", "test", "--prefix", "worker"], cwd=None, description="worker tests"
    )
    _run_tool(
        ["npm", "run", "check", "--prefix", "worker"],
        cwd=None,
        description="wrangler dry-run check",
        env={
            **os.environ,
            "XDG_CONFIG_HOME": "/tmp/sndocs-wrangler",
            "WRANGLER_LOG_PATH": "/tmp/sndocs-wrangler.log",
        },
    )

    _require_clean_workspace([args.state, args.handoff, args.candidate, args.site], args.clean)

    # The bootstrap safety gate runs before any discovery or build work, both
    # so a missing pointer fails fast and so the single --allow-bootstrap flag
    # here is the only place this decision is made for the whole run.
    resolve_ns = types.SimpleNamespace(
        output=args.state / "release-manifest.json",
        github_manifest=None,
        allow_bootstrap=args.allow_bootstrap,
    )
    resolved = resolve_active(resolve_ns, client)
    bootstrap = resolved["state"] == "bootstrap"
    # resolve_active never writes --output in the bootstrap case; there is
    # nothing to read back.
    active_release_path = None if bootstrap else resolve_ns.output
    active_release = None if bootstrap else json.loads(active_release_path.read_bytes())

    settings = load_settings(args.config)
    source_repository = LocalSource(args.source, settings)

    full_discovery = discover(settings, source_repository)
    _write_json(args.state / "discovery.json", full_discovery.to_dict())

    fingerprint = calculate_pipeline_fingerprint(args.config)
    deployment_plan = plan_latest_release(full_discovery.to_dict(), fingerprint, active_release)
    _write_json(args.state / "deployment-plan.json", deployment_plan)

    latest = deployment_plan["latest"]
    latest_discovery = discover(settings, source_repository, (latest,))

    temporary_root = Path.cwd() / ".temp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sndocs-", dir=temporary_root) as work:
        build_site(
            settings,
            args.site,
            Path(work),
            None,
            source_repository,
            latest_discovery,
            build_profile="production",
            cleanup_work=True,
        )
    validate_site(args.site)

    push_family(
        types.SimpleNamespace(
            site=args.site,
            plan=args.state / "deployment-plan.json",
            handoff=args.handoff,
            part_size=args.part_size,
        ),
        client,
    )
    assemble(
        types.SimpleNamespace(
            site=args.site,
            inventory=args.handoff / "family-inventory.json",
            candidate=args.candidate,
            active_release=active_release_path,
        ),
        client,
    )
    pushed = push_candidate(
        types.SimpleNamespace(candidate=args.candidate, part_size=args.part_size), client
    )

    print(
        f"{PREVIEW_CHECKLIST}\nCandidate release: {pushed['release_id']}\n"
        "Preview: https://preview.sndocs.com/\n"
        "Once the checklist above passes, run "
        f"`promote --candidate {args.candidate} --i-reviewed-preview`.",
        file=sys.stderr,
    )
    return {
        "release_id": pushed["release_id"],
        "latest": latest,
        "bootstrap": bootstrap,
        "candidate": str(args.candidate),
    }


PREVIEW_CHECKLIST = """
Manual preview review (this flag is the only record that it happened):
  1. Open the preview root and the latest-family landing page.
  2. Confirm navigation and a representative documentation page render.
  3. Run a Pagefind search and open a result.
  4. Confirm X-Sndocs-Release matches the candidate release id below.
  5. Confirm X-Robots-Tag: noindex, nofollow.
"""


def promote(args, client: R2Client) -> dict:
    """Deploy the candidate to production, verify it, then record it as live."""
    release = _read_json(args.candidate / "release-manifest.json")
    validate_release_manifest(release)
    release_id = release["release_id"]
    if not args.i_reviewed_preview:
        raise PublishError(
            f"{PREVIEW_CHECKLIST}\nCandidate release: {release_id}\n"
            "Re-run with --i-reviewed-preview once the checklist above passes."
        )

    # RELEASE_ID comes from the manifest, never from an argument, so a
    # hand-typed promotion cannot deploy the BOOTSTRAP_REQUIRED sentinel.
    deploy = [
        "npx",
        "wrangler",
        "deploy",
        "--env",
        "production",
        "--var",
        "DEPLOYMENT_MODE:production",
        "--var",
        f"RELEASE_ID:{release_id}",
        "--message",
        f"sndocs release {release_id}",
    ]
    _run_tool(deploy, cwd=args.worker_dir, description="wrangler deploy")

    verify = [
        sys.executable,
        str(args.verifier),
        "--base-url",
        args.base_url,
        "--release",
        str(args.candidate / "release-manifest.json"),
    ]
    try:
        _run_tool(verify, cwd=None, description="deployment verification")
    except PublishError as verify_error:
        try:
            _run_tool(
                ["npx", "wrangler", "rollback", "--env", "production", "--yes"],
                cwd=args.worker_dir,
                description="wrangler rollback",
            )
        except PublishError as rollback_error:
            raise PublishError(
                f"deployment verification failed ({verify_error}), and the "
                f"automatic rollback also failed ({rollback_error}). If this is "
                "the first production deployment, wrangler cannot roll back "
                "because no prior stable Worker version exists yet — that is "
                "expected. Manually verify the live site before retrying, e.g. "
                f"`curl -sSI {args.base_url}` and confirm X-Sndocs-Release."
            ) from rollback_error
        raise PublishError(
            f"{verify_error}; production was rolled back"
        ) from verify_error

    # Only now is this release live.
    client.put_bytes(
        PRODUCTION_POINTER_KEY,
        json.dumps(production_pointer(release_id), indent=2).encode() + b"\n",
        content_type=JSON_CONTENT_TYPE,
        cache_control="no-store",
    )
    return {
        "release_id": release_id,
        "base_url": args.base_url,
        "production_pointer": PRODUCTION_POINTER_KEY,
        "verified": True,
    }


def recovery_manifest(args, client: R2Client) -> dict:
    """Write reconstruction metadata and checksums for the GitHub Release."""
    release = _read_json(args.candidate / "release-manifest.json")
    root_recovery = _read_json(args.candidate / "root-recovery.json")
    reconstruction = build_reconstruction(release, root_recovery)
    _write_json(args.candidate / "reconstruction.json", reconstruction)

    assets = sorted(path for path in args.assets.rglob("*") if path.is_file())
    if not assets:
        raise PublishError(f"no recovery assets found below {args.assets}")
    checksums = args.candidate / "recovery-assets.sha256"
    checksums.write_text(recovery_checksum_manifest(assets), encoding="utf-8")

    result = {
        "release_id": release["release_id"],
        "reconstruction": str(args.candidate / "reconstruction.json"),
        "checksums": str(checksums),
        "assets": len(assets),
        "families_without_recovery": reconstruction["families_without_recovery"],
    }
    if args.print_upload_commands:
        print(
            _format_upload_commands(_upload_command_plan(args, release, reconstruction, assets)),
            file=sys.stderr,
        )
    return result


def _upload_command_plan(
    args, release: dict, reconstruction: dict, assets
) -> list[tuple[list[str] | None, str]]:
    """Return (argv, description) pairs; argv is None for a shell-only comment."""
    latest = release["latest"]
    archive = reconstruction["families"][latest]["name"]
    plan: list[tuple[list[str] | None, str]] = [
        (
            [
                "gh",
                "release",
                "create",
                "site-artifact",
                "--title",
                "Latest sndocs.com recovery artifacts",
                "--notes",
                "Rolling recovery metadata and immutable per-family archives for sndocs.com.",
            ],
            "create the site-artifact release",
        ),
        (None, "Replace the changed family's assets, then refresh the rolling files:"),
        (
            ["gh", "release", "delete-asset", "site-artifact", archive, "--yes"],
            "delete-asset (best-effort; the asset may not exist yet)",
        ),
    ]
    for path in assets:
        plan.append(
            (
                ["gh", "release", "upload", "site-artifact", str(path), "--clobber"],
                f"upload {path.name}",
            )
        )
    for name in ("reconstruction.json", "recovery-assets.sha256", "release-manifest.json"):
        plan.append(
            (
                [
                    "gh",
                    "release",
                    "upload",
                    "site-artifact",
                    str(args.candidate / name),
                    "--clobber",
                ],
                f"upload {name}",
            )
        )
    return plan


def _format_upload_commands(plan: list[tuple[list[str] | None, str]]) -> str:
    lines = [
        "gh release view site-artifact >/dev/null 2>&1 || \\\n"
        '  gh release create site-artifact \\\n'
        '    --title "Latest sndocs.com recovery artifacts" \\\n'
        '    --notes "Rolling recovery metadata and immutable per-family archives for sndocs.com."'
    ]
    for argv, description in plan[1:]:
        if argv is None:
            lines.append(f"# {description}")
        elif argv[2] == "delete-asset":
            lines.append(" ".join(argv) + " || true")
        else:
            lines.append(" ".join(argv))
    return "\n".join(lines)


def _gh_release_exists(name: str) -> bool:
    return subprocess.run(
        ["gh", "release", "view", name], capture_output=True
    ).returncode == 0


def cleanup(args, client: R2Client) -> dict:
    """Plan, and only with --apply perform, guarded deletion of stale objects."""
    active = _read_json(args.candidate / "release-manifest.json")
    rollback = _read_json(args.rollback) if args.rollback else None
    raw = client.list_objects()
    if not raw:
        raise PublishError("bucket listing is empty; refusing to plan a cleanup")
    counted = client.count_objects()
    if counted != len(raw):
        raise PublishError(
            f"bucket listing is inconsistent ({len(raw)} listed, {counted} counted); "
            "a truncated listing would under-protect the plan"
        )

    objects = [
        StoredObject(
            key=item["Key"],
            bytes=item["Size"],
            last_modified=_parse_timestamp(item["LastModified"]),
        )
        for item in raw
    ]
    public = [active] + ([rollback] if rollback else [])
    plan = plan_cleanup(
        objects,
        active,
        rollback,
        public,
        require_recovery=not args.allow_missing_recovery,
    )
    _write_json(args.candidate / "cleanup-plan.json", plan)

    applied = 0
    if args.apply:
        if rollback is None:
            raise PublishError(
                "refusing to delete without a rollback release; the first "
                "publication is plan-only by design"
            )
        destination = args.candidate / "cleanup-batches"
        for batch in _write_batches(plan, destination):
            client.delete_batch(batch)
            applied += 1
    return {
        "plan": str(args.candidate / "cleanup-plan.json"),
        "plan_sha256": plan["plan_sha256"],
        "delete_count": plan["delete_count"],
        "delete_bytes": plan["delete_bytes"],
        "retained_count": plan["retained_count"],
        "applied_batches": applied,
        "applied": bool(args.apply),
    }


def finish(args, client: R2Client) -> dict:
    """Write the recovery manifest, push it to GitHub, and plan cleanup."""
    _require_clean_workspace([args.assets], args.clean)
    args.assets.mkdir(parents=True, exist_ok=True)
    for source in (args.handoff / "recovery" / "assets", args.candidate / "recovery" / "assets"):
        if not source.is_dir():
            raise PublishError(f"{source} is missing; run stage before finish")
        for path in sorted(source.iterdir()):
            if path.is_file():
                shutil.copy2(path, args.assets / path.name)

    recovery = recovery_manifest(
        types.SimpleNamespace(
            candidate=args.candidate, assets=args.assets, print_upload_commands=False
        ),
        client,
    )
    release = _read_json(args.candidate / "release-manifest.json")
    reconstruction = _read_json(args.candidate / "reconstruction.json")
    assets = sorted(path for path in args.assets.rglob("*") if path.is_file())
    plan = _upload_command_plan(args, release, reconstruction, assets)

    create_argv, _create_description = plan[0]
    gh_commands: list[str] = []
    if not _gh_release_exists("site-artifact"):
        _run_tool(create_argv, cwd=None, description="gh release create")
        gh_commands.append(" ".join(create_argv))
    for argv, description in plan[1:]:
        if argv is None:
            continue
        if description.startswith("delete-asset"):
            try:
                _run_tool(argv, cwd=None, description=description)
            except PublishError:
                pass
        else:
            _run_tool(argv, cwd=None, description=description)
        gh_commands.append(" ".join(argv))

    cleanup_result = cleanup(
        types.SimpleNamespace(
            candidate=args.candidate,
            rollback=args.rollback,
            apply=False,
            allow_missing_recovery=args.allow_missing_recovery,
        ),
        client,
    )
    return {
        "recovery": recovery,
        "gh_commands": gh_commands,
        "cleanup_plan": cleanup_result,
    }


def _parse_timestamp(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_batches(plan: dict, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    rows = plan.get("delete", [])
    written = []
    for index in range(0, len(rows), 1000):
        path = destination / f"batch-{index // 1000 + 1:04d}.json"
        _write_json(
            path,
            {
                "Objects": [
                    {"Key": item["key"]} for item in rows[index : index + 1000]
                ],
                "Quiet": False,
            },
        )
        written.append(path)
    return written


def _run_tool(
    argv: list[str], *, cwd: Path | None, description: str, env: dict[str, str] | None = None
) -> None:
    completed = subprocess.run(argv, cwd=cwd, env=env)
    if completed.returncode != 0:
        raise PublishError(f"{description} failed with exit status {completed.returncode}")


# -- argument parsing -------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m sndocs.publish_cli",
        description="Publish an sndocs.com release from an operator workstation",
    )
    commands = result.add_subparsers(dest="command", required=True)

    stage_command = commands.add_parser(
        "stage",
        help="run preflight, then discovery through push-candidate, in one command",
    )
    stage_command.add_argument("--source", type=Path, required=True)
    stage_command.add_argument("--config", type=Path, default=Path("pipeline.toml"))
    stage_command.add_argument("--state", type=Path, default=Path("state"))
    stage_command.add_argument("--handoff", type=Path, default=Path("handoff"))
    stage_command.add_argument("--candidate", type=Path, default=Path("candidate"))
    stage_command.add_argument("--site", type=Path, default=Path("site"))
    stage_command.add_argument("--allow-bootstrap", action="store_true")
    stage_command.add_argument("--clean", action="store_true")
    stage_command.add_argument("--part-size", type=int, default=DEFAULT_PART_SIZE)

    active = commands.add_parser(
        "resolve-active", help="record which release is currently live"
    )
    active.add_argument("--output", type=Path, required=True)
    active.add_argument("--github-manifest", type=Path)
    active.add_argument("--allow-bootstrap", action="store_true")

    family = commands.add_parser(
        "push-family", help="package and immutably upload the built latest family"
    )
    family.add_argument("--site", type=Path, required=True)
    family.add_argument("--plan", type=Path, required=True)
    family.add_argument("--handoff", type=Path, default=Path("handoff"))
    family.add_argument("--part-size", type=int, default=DEFAULT_PART_SIZE)

    candidate = commands.add_parser(
        "assemble-candidate", help="build the candidate release root"
    )
    candidate.add_argument("--site", type=Path, required=True)
    candidate.add_argument("--inventory", type=Path, required=True)
    candidate.add_argument("--candidate", type=Path, default=Path("candidate"))
    candidate_active = candidate.add_mutually_exclusive_group(required=True)
    candidate_active.add_argument("--active-release", type=Path)
    candidate_active.add_argument("--no-active-release", action="store_true")

    push = commands.add_parser(
        "push-candidate", help="upload the candidate root, manifest, and preview pointer"
    )
    push.add_argument("--candidate", type=Path, default=Path("candidate"))
    push.add_argument("--part-size", type=int, default=DEFAULT_PART_SIZE)

    promotion = commands.add_parser(
        "promote", help="deploy the candidate to production and record it as live"
    )
    promotion.add_argument("--candidate", type=Path, default=Path("candidate"))
    promotion.add_argument("--i-reviewed-preview", action="store_true")
    promotion.add_argument("--base-url", default="https://sndocs.com")
    promotion.add_argument("--worker-dir", type=Path, default=Path("worker"))
    promotion.add_argument(
        "--verifier", type=Path, default=Path("scripts/verify_deployment.py")
    )

    recovery = commands.add_parser(
        "recovery-manifest", help="write reconstruction metadata and checksums"
    )
    recovery.add_argument("--candidate", type=Path, default=Path("candidate"))
    recovery.add_argument("--assets", type=Path, required=True)
    recovery.add_argument("--print-upload-commands", action="store_true")

    prune = commands.add_parser("cleanup", help="plan, and optionally apply, deletion")
    prune.add_argument("--candidate", type=Path, default=Path("candidate"))
    prune.add_argument("--rollback", type=Path)
    prune.add_argument("--apply", action="store_true")
    prune.add_argument("--allow-missing-recovery", action="store_true")

    finish_command = commands.add_parser(
        "finish", help="write the recovery manifest, push it to GitHub, and plan cleanup"
    )
    finish_command.add_argument("--candidate", type=Path, default=Path("candidate"))
    finish_command.add_argument("--handoff", type=Path, default=Path("handoff"))
    finish_command.add_argument("--assets", type=Path, default=Path("release-assets"))
    finish_command.add_argument("--rollback", type=Path)
    finish_command.add_argument("--allow-missing-recovery", action="store_true")
    finish_command.add_argument("--clean", action="store_true")
    return result


HANDLERS = {
    "stage": stage,
    "resolve-active": resolve_active,
    "push-family": push_family,
    "assemble-candidate": assemble,
    "push-candidate": push_candidate,
    "promote": promote,
    "recovery-manifest": recovery_manifest,
    "cleanup": cleanup,
    "finish": finish,
}


def main(argv: list[str] | None = None, client: R2Client | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        resolved = client or R2Client(R2Config.from_env())
        result = HANDLERS[args.command](args, resolved)
    except (PublishError, R2Error, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"publish error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
