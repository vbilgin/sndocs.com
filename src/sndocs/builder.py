from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__
from .discovery import discover
from .models import Discovery, Settings
from .navigation import parse_index
from .source import RemoteSource, SourceRepository
from .transform import transform_tree

MANIFEST_NAME = "build-manifest.json"
LINK_REPORT_NAME = "link-report.json"


def pipeline_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root / "pyproject.toml", root / "pipeline.toml"]
    paths += sorted((root / "src" / "sndocs").rglob("*"))
    for path in paths:
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def read_manifest(site: Path | None) -> dict:
    if not site:
        return {}
    path = site / MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def publication_nav(source: Path, discovery: Discovery) -> list[dict]:
    nav: list[dict] = []
    for publication in discovery.publications:
        index = source / "markdown" / publication.slug / "index.md"
        if not index.exists():
            continue
        children = parse_index(index.read_text(encoding="utf-8", errors="replace"))
        items: list = [f"{publication.slug}/index.md", *children]
        nav.append({publication.name: items})
    return nav


def write_mkdocs_config(settings: Settings, source: Path, work: Path, family: str, discovery: Discovery) -> Path:
    config = {
        "site_name": f"{settings.site_name} — {family.title()}",
        "site_description": settings.site_description,
        "site_url": f"{settings.site_url}/{family}/" if settings.site_url else "",
        "docs_dir": str(work / "docs"),
        "site_dir": str(work / "site"),
        "theme": {
            "name": "material",
            "custom_dir": str(settings.root / "src" / "sndocs" / "theme"),
            "features": ["navigation.indexes", "navigation.top", "navigation.footer", "search.suggest", "content.code.copy"],
            "palette": [{"scheme": "default", "primary": "blue grey", "accent": "teal"}],
        },
        "plugins": [{"search": {"lang": "en"}}],
        "markdown_extensions": ["admonition", "attr_list", "tables", "toc", "pymdownx.details", "pymdownx.superfences"],
        "extra_css": ["assets/stylesheets/extra.css"],
        "extra_javascript": ["assets/javascripts/versions.js"],
        "nav": publication_nav(source, discovery),
        "copyright": "Independent community mirror. ServiceNow content used under Apache-2.0.",
        "strict": True,
    }
    path = work / "mkdocs.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def build_family(
    settings: Settings, discovery: Discovery, family: str, work_root: Path, output: Path,
    source_repository: SourceRepository,
) -> dict:
    work = work_root / family
    source = work / "source"
    source_repository.materialize(settings, family, discovery.shas[family], source)
    docs = work / "docs"
    link_report = transform_tree(
        source / "markdown", docs, family, set(discovery.families), settings.repository
    )
    config = write_mkdocs_config(settings, source, work, family, discovery)
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--clean", "--config-file", str(config)], check=True)
    shutil.copytree(work / "site", output / family, dirs_exist_ok=True)
    return link_report


def read_link_reports(site: Path | None) -> dict[str, dict]:
    if not site:
        return {}
    path = site / LINK_REPORT_NAME
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("families", {})


def empty_link_report(family: str) -> dict:
    return {
        "family": family,
        "counts": {"exact": 0, "repaired": 0, "placeholder": 0, "ambiguous": 0},
        "repairs": [],
        "placeholders": [],
    }


def build_site(
    settings: Settings, output: Path, work: Path, previous_site: Path | None = None,
    source_repository: SourceRepository | None = None, discovery_result: Discovery | None = None,
) -> tuple[dict, bool]:
    source_repository = source_repository or RemoteSource()
    discovery = discovery_result or discover(settings, source_repository)
    previous = read_manifest(previous_site)
    previous_link_reports = read_link_reports(previous_site)
    fingerprint = pipeline_fingerprint(settings.root)
    previous_families = previous.get("families", {})
    force_all = previous.get("pipeline_fingerprint") != fingerprint
    changed = force_all or previous.get("latest") != discovery.latest
    output.mkdir(parents=True, exist_ok=True)
    family_records: dict[str, dict] = {}
    family_link_reports: dict[str, dict] = {}

    for family in discovery.families:
        sha = discovery.shas[family]
        old = previous_families.get(family, {})
        can_reuse = not force_all and old.get("source_sha") == sha and previous_site and (previous_site / family).is_dir()
        if can_reuse:
            shutil.copytree(previous_site / family, output / family, dirs_exist_ok=True)
            family_link_reports[family] = previous_link_reports.get(family, empty_link_report(family))
        else:
            family_link_reports[family] = build_family(
                settings, discovery, family, work, output, source_repository
            )
            changed = True
        family_records[family] = {
            "source_sha": sha,
            "archived": False,
            "path": f"/{family}/",
            "link_counts": family_link_reports[family]["counts"],
        }

    for family, record in previous_families.items():
        if family in family_records or not previous_site or not (previous_site / family).is_dir():
            continue
        shutil.copytree(previous_site / family, output / family, dirs_exist_ok=True)
        family_link_reports[family] = previous_link_reports.get(family, empty_link_report(family))
        family_records[family] = {
            **record,
            "archived": True,
            "path": f"/{family}/",
            "link_counts": family_link_reports[family]["counts"],
        }
        changed = changed or not record.get("archived", False)

    versions = {
        "latest": discovery.latest,
        "versions": [
            {"family": family, "title": family.title(), "path": record["path"], "archived": record["archived"]}
            for family, record in family_records.items()
        ],
    }
    (output / "versions.json").write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")
    aggregate_link_report = {"schema_version": 1, "families": family_link_reports}
    (output / LINK_REPORT_NAME).write_text(
        json.dumps(aggregate_link_report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=./{discovery.latest}/">'
        f'<link rel="canonical" href="./{discovery.latest}/"><title>sndocs.com</title>', encoding="utf-8"
    )
    upstream_license = """              Copyright 2026 ServiceNow

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
    (output / "SERVICENOW-LICENSE.txt").write_text(upstream_license, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "pipeline_version": __version__,
        "pipeline_fingerprint": fingerprint,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "upstream_repository": settings.repository,
        "latest": discovery.latest,
        "families": family_records,
    }
    (output / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for family, report in family_link_reports.items():
        counts = report["counts"]
        print(
            f"Link resolution [{family}]: {counts['exact']} exact, {counts['repaired']} repaired, "
            f"{counts['placeholder']} placeholders, {counts['ambiguous']} ambiguous"
        )
    return manifest, changed
