"""Shared fixtures for deployment and publication tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sndocs.builder import empty_link_counts
from sndocs.deployment import assemble_candidate, build_family_inventory

FINGERPRINT = "f" * 64


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def production_site(tmp_path: Path, family: str, sha: str, *, text: str = "page") -> Path:
    """A minimal single-family production site that passes inventory checks."""
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
    (pagefind / "index" / "en_fixture.pf_index").write_text("index", encoding="utf-8")
    (site / "index.html").write_text(
        f'<meta http-equiv="refresh" content="0; url=./{family}/">',
        encoding="utf-8",
    )
    (site / "SERVICENOW-LICENSE.txt").write_text("license", encoding="utf-8")
    counts = empty_link_counts()
    write_json(
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
    write_json(
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
    write_json(
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


def recovery_archive(family: str) -> dict:
    """Recovery archive metadata shaped like ``deployment_cli package`` output."""
    name = f"sndocs-{family}.tar.gz"
    digest = hashlib.sha256(name.encode()).hexdigest()
    return {
        "name": name,
        "bytes": 1024,
        "sha256": digest,
        "parts": [{"name": name, "bytes": 1024, "sha256": digest}],
    }


def release(tmp_path: Path, family: str, sha: str, *, with_recovery: bool = False):
    site = production_site(tmp_path, family, sha)
    inventory = build_family_inventory(
        site,
        family,
        sha,
        FINGERPRINT,
        created_at="2026-01-01T00:00:00+00:00",
        recovery_archive=recovery_archive(family) if with_recovery else None,
    )
    root = tmp_path / f"root-{family}"
    manifest = assemble_candidate(
        site,
        root,
        inventory,
        created_at="2026-01-01T00:00:00+00:00",
    )
    return site, root, inventory, manifest
