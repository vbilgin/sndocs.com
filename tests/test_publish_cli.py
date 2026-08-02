from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from support import FINGERPRINT, production_site, recovery_archive, release

from sndocs import publish_cli
from sndocs.deployment import plan_latest_release, production_pointer

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


class FakeR2:
    """In-memory stand-in for the bucket, recording write order."""

    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects: dict[str, bytes] = dict(objects or {})
        self.writes: list[str] = []
        self.uploaded_trees: list[str] = []

    # reads
    def list_objects(self, prefix: str = "") -> list[dict]:
        return [
            {
                "Key": key,
                "Size": len(value),
                "LastModified": NOW.isoformat().replace("+00:00", "Z"),
            }
            for key, value in sorted(self.objects.items())
            if key.startswith(prefix)
        ]

    def count_objects(self, prefix: str = "") -> int:
        return len(self.list_objects(prefix))

    def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def get_tree(self, prefix: str, local: Path) -> None:
        listed = prefix.rstrip("/") + "/"
        local.mkdir(parents=True, exist_ok=True)
        for key, value in self.objects.items():
            if key.startswith(listed):
                target = local / key[len(listed) :]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value)

    # writes
    def put_bytes(self, key, data, *, content_type, cache_control=None) -> None:
        self.objects[key] = data
        self.writes.append(key)

    def put_tree(self, local: Path, prefix: str) -> None:
        listed = prefix.rstrip("/") + "/"
        for path in sorted(local.rglob("*")):
            if path.is_file():
                key = listed + path.relative_to(local).as_posix()
                self.objects[key] = path.read_bytes()
                self.writes.append(key)
        self.uploaded_trees.append(prefix)

    def delete_batch(self, payload: Path) -> dict:
        keys = [item["Key"] for item in json.loads(payload.read_text())["Objects"]]
        for key in keys:
            self.objects.pop(key, None)
        return {"Deleted": [{"Key": key} for key in keys]}


def _live_bucket(tmp_path: Path, family: str = "yokohama", sha: str = "sha-1"):
    """A bucket whose production pointer names a valid, complete release."""
    _site, root, _inventory, manifest = release(
        tmp_path, family, sha, with_recovery=True
    )
    release_id = manifest["release_id"]
    body = json.dumps(manifest, indent=2).encode() + b"\n"
    objects = {
        f"releases/{release_id}.json": body,
        publish_cli.PRODUCTION_POINTER_KEY: json.dumps(
            production_pointer(release_id)
        ).encode(),
    }
    for path in sorted(root.rglob("*")):
        if path.is_file():
            objects[f"{manifest['root_prefix']}/{path.relative_to(root).as_posix()}"] = (
                path.read_bytes()
            )
    return FakeR2(objects), manifest, body


def _plan(tmp_path: Path, family: str, sha: str, active: dict | None) -> Path:
    plan = plan_latest_release(
        {"latest": family, "shas": {family: sha}}, FINGERPRINT, active
    )
    path = tmp_path / "deployment-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


# -- resolve-active ---------------------------------------------------------


def test_resolve_active_fails_closed_when_nothing_is_live(tmp_path, capsys):
    status = publish_cli.main(
        ["resolve-active", "--output", str(tmp_path / "active.json")],
        client=FakeR2(),
    )

    assert status == 2
    error = capsys.readouterr().err
    assert "the live release is unknown" in error
    assert "drop every archived family" in error
    assert not (tmp_path / "active.json").exists()


def test_resolve_active_bootstrap_is_opt_in_and_refuses_a_stale_manifest(tmp_path):
    output = tmp_path / "active.json"

    status = publish_cli.main(
        ["resolve-active", "--output", str(output), "--allow-bootstrap"],
        client=FakeR2(),
    )
    assert status == 0
    assert not output.exists()

    output.write_text("{}", encoding="utf-8")
    assert (
        publish_cli.main(
            ["resolve-active", "--output", str(output), "--allow-bootstrap"],
            client=FakeR2(),
        )
        == 2
    )


def test_resolve_active_writes_the_live_manifest_verbatim(tmp_path, capsys):
    client, manifest, body = _live_bucket(tmp_path)
    output = tmp_path / "active.json"

    status = publish_cli.main(
        ["resolve-active", "--output", str(output)], client=client
    )

    assert status == 0
    # Byte-identical, so a later comparison against the GitHub copy is meaningful.
    assert output.read_bytes() == body
    result = json.loads(capsys.readouterr().out)
    assert result["release_id"] == manifest["release_id"]
    assert result["families"] == ["yokohama"]


def test_resolve_active_rejects_a_dangling_pointer(tmp_path, capsys):
    client, manifest, _body = _live_bucket(tmp_path)
    del client.objects[f"releases/{manifest['release_id']}.json"]

    status = publish_cli.main(
        ["resolve-active", "--output", str(tmp_path / "active.json")], client=client
    )

    assert status == 2
    assert "does not exist" in capsys.readouterr().err


def test_resolve_active_rejects_an_altered_manifest(tmp_path, capsys):
    client, manifest, _body = _live_bucket(tmp_path)
    tampered = {**manifest, "latest": "yokohama", "created_at": "2026-01-02T00:00:00"}
    client.objects[f"releases/{manifest['release_id']}.json"] = json.dumps(
        tampered
    ).encode()

    status = publish_cli.main(
        ["resolve-active", "--output", str(tmp_path / "active.json")], client=client
    )

    assert status == 2
    assert "release ID does not match" in capsys.readouterr().err


def test_resolve_active_compares_the_github_recovery_copy(tmp_path, capsys):
    client, _manifest, body = _live_bucket(tmp_path)
    divergent = tmp_path / "github-manifest.json"
    divergent.write_bytes(body + b" ")

    status = publish_cli.main(
        [
            "resolve-active",
            "--output",
            str(tmp_path / "active.json"),
            "--github-manifest",
            str(divergent),
        ],
        client=client,
    )

    assert status == 2
    assert "differs from R2" in capsys.readouterr().err


# -- push-family ------------------------------------------------------------


def test_push_family_refuses_when_the_plan_reports_no_change(tmp_path, capsys):
    client, manifest, _body = _live_bucket(tmp_path)
    site = production_site(tmp_path / "rebuild", "yokohama", "sha-1")
    plan = _plan(tmp_path, "yokohama", "sha-1", manifest)

    status = publish_cli.main(
        [
            "push-family",
            "--site",
            str(site),
            "--plan",
            str(plan),
            "--handoff",
            str(tmp_path / "handoff"),
        ],
        client=client,
    )

    assert status == 2
    assert "no change" in capsys.readouterr().err


def test_push_family_uploads_once_then_reuses_the_immutable_prefix(tmp_path, capsys):
    client = FakeR2()
    site = production_site(tmp_path, "zurich", "sha-2")
    plan = _plan(tmp_path, "zurich", "sha-2", None)
    argv = [
        "push-family",
        "--site",
        str(site),
        "--plan",
        str(plan),
        "--handoff",
        str(tmp_path / "handoff"),
    ]

    assert publish_cli.main(argv, client=client) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["reused"] is False
    assert first["object_count"] > 0
    inventory = json.loads(
        (tmp_path / "handoff" / "family-inventory.json").read_text()
    )
    assert inventory["recovery"]["prefix"].startswith("recovery/families/zurich/")

    # A rerun must verify rather than overwrite.
    trees = list(client.uploaded_trees)
    assert publish_cli.main(argv, client=client) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["reused"] is True
    assert client.uploaded_trees.count(inventory["prefix"]) == trees.count(
        inventory["prefix"]
    )


def test_push_family_reports_divergence_instead_of_overwriting(tmp_path, capsys):
    client = FakeR2()
    site = production_site(tmp_path, "zurich", "sha-2")
    plan = _plan(tmp_path, "zurich", "sha-2", None)
    prefix = json.loads(plan.read_text())["content_prefix"]
    client.objects[f"{prefix}/unexpected.html"] = b"stale"

    status = publish_cli.main(
        [
            "push-family",
            "--site",
            str(site),
            "--plan",
            str(plan),
            "--handoff",
            str(tmp_path / "handoff"),
        ],
        client=client,
    )

    assert status == 2
    error = capsys.readouterr().err
    assert "immutable prefix diverges" in error
    assert "Do not overwrite" in error
    assert client.objects[f"{prefix}/unexpected.html"] == b"stale"


# -- candidate assembly and upload ------------------------------------------


def _candidate(tmp_path: Path, client: FakeR2, active: Path | None) -> Path:
    site = production_site(tmp_path, "zurich", "sha-2")
    plan = _plan(tmp_path, "zurich", "sha-2", None)
    assert (
        publish_cli.main(
            [
                "push-family",
                "--site",
                str(site),
                "--plan",
                str(plan),
                "--handoff",
                str(tmp_path / "handoff"),
            ],
            client=client,
        )
        == 0
    )
    argv = [
        "assemble-candidate",
        "--site",
        str(site),
        "--inventory",
        str(tmp_path / "handoff" / "family-inventory.json"),
        "--candidate",
        str(tmp_path / "candidate"),
    ]
    argv += ["--active-release", str(active)] if active else ["--no-active-release"]
    assert publish_cli.main(argv, client=client) == 0
    return tmp_path / "candidate"


def test_assembly_retains_archived_families_from_the_live_release(tmp_path):
    client, _manifest, body = _live_bucket(tmp_path)
    active = tmp_path / "active.json"
    active.write_bytes(body)

    candidate = _candidate(tmp_path, client, active)

    release = json.loads((candidate / "release-manifest.json").read_text())
    assert list(release["families"]) == ["zurich", "yokohama"]
    assert release["families"]["zurich"]["archived"] is False
    assert release["families"]["yokohama"]["archived"] is True


def test_push_candidate_uploads_the_manifest_last_and_reads_it_back(tmp_path, capsys):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    release_id = json.loads(
        (candidate / "release-manifest.json").read_text()
    )["release_id"]
    client.writes.clear()
    capsys.readouterr()

    assert (
        publish_cli.main(
            ["push-candidate", "--candidate", str(candidate)], client=client
        )
        == 0
    )

    manifest_key = f"releases/{release_id}.json"
    writes = client.writes
    assert manifest_key in writes
    # Nothing but the preview pointer may follow the manifest.
    assert writes[writes.index(manifest_key) + 1 :] == [
        publish_cli.PREVIEW_POINTER_KEY
    ]
    assert client.objects[manifest_key] == (
        candidate / "release-manifest.json"
    ).read_bytes()
    pointer = json.loads(client.objects[publish_cli.PREVIEW_POINTER_KEY])
    assert pointer == {"schema_version": 1, "release_id": release_id}


def test_push_candidate_refuses_a_manifest_that_reads_back_differently(
    tmp_path, capsys
):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    capsys.readouterr()

    original = client.put_bytes

    def corrupting(key, data, *, content_type, cache_control=None):
        is_manifest = key.startswith("releases/") and key.endswith(".json")
        original(
            key,
            b"corrupted" if is_manifest else data,
            content_type=content_type,
            cache_control=cache_control,
        )

    client.put_bytes = corrupting

    status = publish_cli.main(
        ["push-candidate", "--candidate", str(candidate)], client=client
    )

    assert status == 2
    assert "read back differently" in capsys.readouterr().err
    assert publish_cli.PREVIEW_POINTER_KEY not in client.objects


# -- promote ----------------------------------------------------------------


def test_promote_prints_the_checklist_and_refuses_without_the_flag(tmp_path, capsys):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    capsys.readouterr()

    status = publish_cli.main(
        ["promote", "--candidate", str(candidate)], client=client
    )

    assert status == 2
    error = capsys.readouterr().err
    assert "Pagefind search" in error
    assert "--i-reviewed-preview" in error
    assert publish_cli.PRODUCTION_POINTER_KEY not in client.objects


def test_promote_records_the_pointer_only_after_verification(tmp_path, capsys, monkeypatch):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    capsys.readouterr()
    invoked = []

    def fake_tool(argv, *, cwd, description):
        invoked.append(description)

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)

    assert (
        publish_cli.main(
            ["promote", "--candidate", str(candidate), "--i-reviewed-preview"],
            client=client,
        )
        == 0
    )

    assert invoked == ["wrangler deploy", "deployment verification"]
    assert client.writes[-1] == publish_cli.PRODUCTION_POINTER_KEY
    release_id = json.loads(
        (candidate / "release-manifest.json").read_text()
    )["release_id"]
    assert json.loads(client.objects[publish_cli.PRODUCTION_POINTER_KEY]) == {
        "schema_version": 1,
        "release_id": release_id,
    }


def test_promote_rolls_back_and_leaves_the_pointer_alone_on_failure(
    tmp_path, capsys, monkeypatch
):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    capsys.readouterr()
    invoked = []

    def fake_tool(argv, *, cwd, description):
        invoked.append(description)
        if description == "deployment verification":
            raise publish_cli.PublishError("release header mismatch")

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)

    status = publish_cli.main(
        ["promote", "--candidate", str(candidate), "--i-reviewed-preview"],
        client=client,
    )

    assert status == 2
    assert "rolled back" in capsys.readouterr().err
    assert invoked == [
        "wrangler deploy",
        "deployment verification",
        "wrangler rollback",
    ]
    assert publish_cli.PRODUCTION_POINTER_KEY not in client.objects


def test_promote_reports_both_failures_when_rollback_also_fails(
    tmp_path, capsys, monkeypatch
):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    capsys.readouterr()
    invoked = []

    def fake_tool(argv, *, cwd, description):
        invoked.append(description)
        if description == "deployment verification":
            raise publish_cli.PublishError("release header mismatch")
        if description == "wrangler rollback":
            raise publish_cli.PublishError(
                "Could not find stable Worker Version to rollback to"
            )

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)

    status = publish_cli.main(
        ["promote", "--candidate", str(candidate), "--i-reviewed-preview"],
        client=client,
    )

    assert status == 2
    error = capsys.readouterr().err
    assert "release header mismatch" in error
    assert "Could not find stable Worker Version to rollback to" in error
    assert "first production deployment" in error
    assert invoked == [
        "wrangler deploy",
        "deployment verification",
        "wrangler rollback",
    ]
    assert publish_cli.PRODUCTION_POINTER_KEY not in client.objects


def test_promote_pins_the_release_id_from_the_manifest(tmp_path, capsys, monkeypatch):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    capsys.readouterr()
    release_id = json.loads(
        (candidate / "release-manifest.json").read_text()
    )["release_id"]
    commands = []

    monkeypatch.setattr(
        publish_cli,
        "_run_tool",
        lambda argv, *, cwd, description: commands.append(argv),
    )
    publish_cli.main(
        ["promote", "--candidate", str(candidate), "--i-reviewed-preview"],
        client=client,
    )

    deploy = commands[0]
    assert f"RELEASE_ID:{release_id}" in deploy
    assert "BOOTSTRAP_REQUIRED" not in " ".join(deploy)


# -- recovery and cleanup ---------------------------------------------------


def test_recovery_manifest_orders_checksums_by_name(tmp_path, capsys):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    assert (
        publish_cli.main(
            ["push-candidate", "--candidate", str(candidate)], client=client
        )
        == 0
    )
    assets = tmp_path / "release-assets"
    assets.mkdir()
    for name in ("sndocs-zurich.tar.gz", "a-first.tar.gz", "m-middle.tar.gz"):
        (assets / name).write_bytes(name.encode())
    capsys.readouterr()

    assert (
        publish_cli.main(
            [
                "recovery-manifest",
                "--candidate",
                str(candidate),
                "--assets",
                str(assets),
            ],
            client=client,
        )
        == 0
    )

    rows = (candidate / "recovery-assets.sha256").read_text().splitlines()
    names = [row.split("  ", 1)[1] for row in rows]
    assert names == sorted(names)
    reconstruction = json.loads((candidate / "reconstruction.json").read_text())
    assert reconstruction["families"]["zurich"]["name"] == "sndocs-zurich.tar.gz"
    assert reconstruction["families_without_recovery"] == []


def test_recovery_manifest_prints_a_create_release_guard_before_upload_commands(
    tmp_path, capsys
):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    assert (
        publish_cli.main(
            ["push-candidate", "--candidate", str(candidate)], client=client
        )
        == 0
    )
    assets = tmp_path / "release-assets"
    assets.mkdir()
    (assets / "sndocs-zurich.tar.gz").write_bytes(b"data")
    capsys.readouterr()

    assert (
        publish_cli.main(
            [
                "recovery-manifest",
                "--candidate",
                str(candidate),
                "--assets",
                str(assets),
                "--print-upload-commands",
            ],
            client=client,
        )
        == 0
    )

    error = capsys.readouterr().err
    lines = error.splitlines()
    assert lines[0] == "gh release view site-artifact >/dev/null 2>&1 || \\"
    assert '--title "Latest sndocs.com recovery artifacts"' in error
    assert (
        '--notes "Rolling recovery metadata and immutable per-family archives '
        'for sndocs.com."' in error
    )
    assert error.index("gh release create site-artifact") < error.index(
        "gh release delete-asset site-artifact"
    )


def test_cleanup_is_plan_only_and_refuses_to_apply_without_a_rollback(
    tmp_path, capsys
):
    client = FakeR2()
    candidate = _candidate(tmp_path, client, None)
    assert (
        publish_cli.main(
            ["push-candidate", "--candidate", str(candidate)], client=client
        )
        == 0
    )
    client.objects["content/orphan/dead/index.html"] = b"stale"
    capsys.readouterr()

    assert (
        publish_cli.main(["cleanup", "--candidate", str(candidate)], client=client)
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["applied"] is False
    assert (candidate / "cleanup-plan.json").exists()
    assert "content/orphan/dead/index.html" in client.objects

    assert (
        publish_cli.main(
            ["cleanup", "--candidate", str(candidate), "--apply"], client=client
        )
        == 2
    )
    assert "without a rollback release" in capsys.readouterr().err


# -- stage --------------------------------------------------------------


def _noop_run_tool(monkeypatch, invoked: list[str] | None = None):
    def fake_tool(argv, *, cwd, description, env=None):
        if invoked is not None:
            invoked.append(description)

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)


def _fake_stage_build_dependencies(monkeypatch, *, family: str = "zurich", sha: str = "sha-2"):
    """Fake discovery/build/validation so stage() tests exercise orchestration
    only; discover/build_site/validate_site have their own dedicated suites."""

    class FakeDiscovery:
        latest = family
        families = [family]
        shas = {family: sha}

        def to_dict(self) -> dict:
            return {"latest": family, "families": [family], "shas": {family: sha}}

    def fake_load_settings(config):
        return object()

    def fake_local_source(source, settings):
        return object()

    def fake_discover(settings, source_repository, family_allowlist=None):
        return FakeDiscovery()

    def fake_build_site(
        settings,
        output,
        work,
        previous_site,
        source_repository,
        discovery_result,
        *,
        build_profile,
        cleanup_work,
    ):
        produced = production_site(output.parent, family, sha)
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(produced), str(output))
        return {"latest": family}, True

    monkeypatch.setattr(publish_cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(publish_cli, "LocalSource", fake_local_source)
    monkeypatch.setattr(publish_cli, "discover", fake_discover)
    monkeypatch.setattr(publish_cli, "build_site", fake_build_site)
    monkeypatch.setattr(publish_cli, "validate_site", lambda site: None)
    monkeypatch.setattr(
        publish_cli, "calculate_pipeline_fingerprint", lambda config: FINGERPRINT
    )


def _stage_workspace_args(tmp_path: Path) -> list[str]:
    """Scope every stage() working directory into tmp_path.

    Never rely on stage's real defaults (state/handoff/candidate/site at the
    repo root) in a test — this repo's own working directories live at those
    exact paths, and a test passing --clean against the real defaults would
    delete them.
    """
    return [
        "--state",
        str(tmp_path / "state"),
        "--handoff",
        str(tmp_path / "handoff"),
        "--candidate",
        str(tmp_path / "candidate"),
        "--site",
        str(tmp_path / "site"),
    ]


def test_stage_runs_preflight_before_touching_the_filesystem(tmp_path, monkeypatch):
    invoked: list[str] = []

    def fake_tool(argv, *, cwd, description, env=None):
        invoked.append(description)
        if description == "wrangler dry-run check":
            raise publish_cli.PublishError("check failed")

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)

    status = publish_cli.main(
        [
            "stage",
            "--source",
            str(tmp_path / "upstream"),
            *_stage_workspace_args(tmp_path),
        ],
        client=FakeR2(),
    )

    assert status == 2
    assert invoked == ["pytest", "worker tests", "wrangler dry-run check"]
    assert not (tmp_path / "state").exists()


def test_stage_fails_closed_without_allow_bootstrap(tmp_path, monkeypatch, capsys):
    _noop_run_tool(monkeypatch)

    status = publish_cli.main(
        [
            "stage",
            "--source",
            str(tmp_path / "upstream"),
            *_stage_workspace_args(tmp_path),
        ],
        client=FakeR2(),
    )

    assert status == 2
    error = capsys.readouterr().err
    assert "the live release is unknown" in error
    assert "drop every archived family" in error
    assert not (tmp_path / "state").exists()


def test_stage_refuses_stale_working_directories_without_clean(tmp_path, monkeypatch):
    _noop_run_tool(monkeypatch)
    stale = tmp_path / "state"
    stale.mkdir()
    (stale / "marker.json").write_text("{}", encoding="utf-8")

    status = publish_cli.main(
        ["stage", "--source", str(tmp_path / "upstream"), *_stage_workspace_args(tmp_path)],
        client=FakeR2(),
    )

    assert status == 2
    assert (stale / "marker.json").exists()


def test_stage_clean_removes_stale_working_directories_first(tmp_path, monkeypatch):
    _noop_run_tool(monkeypatch)
    stale = tmp_path / "state"
    stale.mkdir()
    (stale / "marker.json").write_text("{}", encoding="utf-8")

    # An empty bucket still fails at the bootstrap gate without
    # --allow-bootstrap, but --clean must have already removed the stale
    # directory before that gate is even reached.
    status = publish_cli.main(
        [
            "stage",
            "--source",
            str(tmp_path / "upstream"),
            *_stage_workspace_args(tmp_path),
            "--clean",
        ],
        client=FakeR2(),
    )

    assert status == 2
    assert not (stale / "marker.json").exists()


def test_stage_propagates_bootstrap_and_prints_the_shared_checklist(
    tmp_path, monkeypatch, capsys
):
    _noop_run_tool(monkeypatch)
    _fake_stage_build_dependencies(monkeypatch)
    captured: dict[str, object] = {}
    real_assemble = publish_cli.assemble

    def spy_assemble(args, client):
        captured["active_release"] = args.active_release
        return real_assemble(args, client)

    monkeypatch.setattr(publish_cli, "assemble", spy_assemble)
    client = FakeR2()
    capsys.readouterr()

    status = publish_cli.main(
        [
            "stage",
            "--source",
            str(tmp_path / "upstream"),
            "--state",
            str(tmp_path / "state"),
            "--handoff",
            str(tmp_path / "handoff"),
            "--candidate",
            str(tmp_path / "candidate"),
            "--site",
            str(tmp_path / "site"),
            "--allow-bootstrap",
        ],
        client=client,
    )

    assert status == 0
    assert captured["active_release"] is None
    captured_output = capsys.readouterr()
    result = json.loads(captured_output.out)
    assert result["bootstrap"] is True
    assert "Manual preview review" in captured_output.err
    assert (tmp_path / "state" / "discovery.json").exists()
    assert (tmp_path / "candidate" / "release-manifest.json").exists()


# -- finish -------------------------------------------------------------


def _finished_candidate(tmp_path: Path, client: FakeR2) -> Path:
    candidate = _candidate(tmp_path, client, None)
    assert (
        publish_cli.main(
            ["push-candidate", "--candidate", str(candidate)], client=client
        )
        == 0
    )
    return candidate


def test_finish_executes_gh_commands_it_previously_only_printed(
    tmp_path, monkeypatch, capsys
):
    client = FakeR2()
    candidate = _finished_candidate(tmp_path, client)
    capsys.readouterr()
    invoked: list[tuple[list[str], str]] = []

    def fake_tool(argv, *, cwd, description, env=None):
        invoked.append((argv, description))

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)
    monkeypatch.setattr(publish_cli, "_gh_release_exists", lambda name: False)

    status = publish_cli.main(
        [
            "finish",
            "--candidate",
            str(candidate),
            "--handoff",
            str(tmp_path / "handoff"),
            "--assets",
            str(tmp_path / "release-assets"),
        ],
        client=client,
    )

    assert status == 0
    argvs = [argv for argv, _description in invoked]
    assert argvs[0][:4] == ["gh", "release", "create", "site-artifact"]
    assert argvs[1][:4] == ["gh", "release", "delete-asset", "site-artifact"]
    upload_argvs = [argv for argv in argvs if argv[2] == "upload"]
    assert len(upload_argvs) >= 4  # family archive, root archive, 3 metadata files
    assert all(argv[-1] == "--clobber" for argv in upload_argvs)


def test_finish_swallows_a_failed_delete_asset_like_the_old_shell_or_true(
    tmp_path, monkeypatch
):
    client = FakeR2()
    candidate = _finished_candidate(tmp_path, client)
    invoked: list[str] = []

    def fake_tool(argv, *, cwd, description, env=None):
        invoked.append(description)
        if description.startswith("delete-asset"):
            raise publish_cli.PublishError("asset does not exist yet")

    monkeypatch.setattr(publish_cli, "_run_tool", fake_tool)
    monkeypatch.setattr(publish_cli, "_gh_release_exists", lambda name: True)

    status = publish_cli.main(
        [
            "finish",
            "--candidate",
            str(candidate),
            "--handoff",
            str(tmp_path / "handoff"),
            "--assets",
            str(tmp_path / "release-assets"),
        ],
        client=client,
    )

    assert status == 0
    assert any(description.startswith("upload") for description in invoked)


def test_finish_plans_cleanup_without_applying_and_without_rollback(
    tmp_path, monkeypatch, capsys
):
    client = FakeR2()
    candidate = _finished_candidate(tmp_path, client)
    capsys.readouterr()
    monkeypatch.setattr(publish_cli, "_run_tool", lambda *a, **k: None)
    monkeypatch.setattr(publish_cli, "_gh_release_exists", lambda name: True)

    status = publish_cli.main(
        [
            "finish",
            "--candidate",
            str(candidate),
            "--handoff",
            str(tmp_path / "handoff"),
            "--assets",
            str(tmp_path / "release-assets"),
        ],
        client=client,
    )

    assert status == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cleanup_plan"]["applied"] is False
    assert (candidate / "cleanup-plan.json").exists()
