from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import yaml

from . import __version__
from .discovery import discover
from .links import FamilyLinkResolver
from .models import Discovery, Settings
from .navigation import parse_index
from .source import RemoteSource, SourceRepository
from .transform import transform_tree, write_missing_placeholders

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


def publication_nav(
    source: Path, discovery: Discovery, resolver: FamilyLinkResolver | None = None
) -> list[dict]:
    nav: list[dict] = []
    for publication in discovery.publications:
        index = source / "markdown" / publication.slug / "index.md"
        if not index.exists():
            continue
        children = parse_index(
            index.read_text(encoding="utf-8", errors="replace"),
            resolver,
            referring_index=PurePosixPath(publication.slug) / "index.md" if resolver else None,
        )
        items: list = [f"{publication.slug}/index.md", *children]
        nav.append({publication.name: items})
    return nav


def write_family_landing(docs: Path, family: str, discovery: Discovery) -> None:
    publications = []
    for publication in discovery.publications:
        if (docs / publication.slug / "index.md").exists():
            title = publication.name.replace("[", "\\[").replace("]", "\\]")
            publications.append(f"- [{title}]({publication.slug}/index.md)")
    content = (
        f"---\ntitle: {family.title()} documentation\nrelease: {family}\n---\n\n"
        f"# {family.title()} documentation\n\n"
        "Select a publication:\n\n"
        + "\n".join(publications)
        + "\n"
    )
    (docs / "index.md").write_text(content, encoding="utf-8")


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _phase(family: str, name: str, started: float, path: Path) -> None:
    print(
        f"Build [{family}] {name}: {time.monotonic() - started:.1f}s, "
        f"{_format_size(_tree_size(path))}"
    )


def write_mkdocs_config(
    settings: Settings,
    source: Path,
    work: Path,
    family: str,
    discovery: Discovery,
    site_dir: Path | None = None,
    search: bool = True,
    nav: list[dict] | None = None,
) -> Path:
    features = [
        "navigation.indexes",
        "navigation.prune",
        "navigation.top",
        "navigation.footer",
        "content.code.copy",
    ]
    if search:
        features.append("search.suggest")
    config = {
        "site_name": f"{settings.site_name} — {family.title()}",
        "site_description": settings.site_description,
        "site_url": f"{settings.site_url}/{family}/" if settings.site_url else "",
        "docs_dir": str(work / "docs"),
        "site_dir": str(site_dir or work / "site"),
        "theme": {
            "name": "material",
            "custom_dir": str(settings.root / "src" / "sndocs" / "theme"),
            "features": features,
            "palette": [{"scheme": "default", "primary": "blue grey", "accent": "teal"}],
        },
        "plugins": [{"search": {"lang": "en"}}] if search else [],
        "markdown_extensions": ["admonition", "attr_list", "tables", "toc", "pymdownx.details", "pymdownx.superfences"],
        "extra_css": ["assets/stylesheets/extra.css"],
        "extra_javascript": ["assets/javascripts/versions.js"],
        "nav": nav if nav is not None else publication_nav(source, discovery),
        "copyright": "Independent community mirror. ServiceNow content used under Apache-2.0.",
        "strict": True,
    }
    path = work / "mkdocs.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def build_family(
    settings: Settings, discovery: Discovery, family: str, work_root: Path, output: Path,
    source_repository: SourceRepository, search: bool = True,
) -> dict:
    work = work_root / family
    source = work / "source"
    started = time.monotonic()
    print(f"Build [{family}] materializing source")
    source_repository.materialize(settings, family, discovery.shas[family], source)
    _phase(family, "source ready", started, source)
    docs = work / "docs"
    resolver = FamilyLinkResolver(source / "markdown", family)
    started = time.monotonic()
    print(f"Build [{family}] transforming Markdown")
    transform_tree(
        source / "markdown",
        docs,
        family,
        set(discovery.families),
        settings.repository,
        resolver,
        finalize=False,
    )
    nav = publication_nav(source, discovery, resolver)
    write_missing_placeholders(docs, resolver)
    write_family_landing(docs, family, discovery)
    link_report = resolver.report()
    _phase(family, "Markdown ready", started, docs)
    family_output = output / family
    config = write_mkdocs_config(
        settings,
        source,
        work,
        family,
        discovery,
        site_dir=family_output,
        search=search,
        nav=nav,
    )
    started = time.monotonic()
    print(f"Build [{family}] rendering MkDocs site ({'search enabled' if search else 'search disabled'})")
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--clean", "--config-file", str(config)], check=True)
    _phase(family, "site ready", started, family_output)
    return link_report


def copy_reused_family(source: Path, destination: Path) -> str:
    try:
        shutil.copytree(source, destination, copy_function=os.link)
        return "hard-linked"
    except OSError:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        return "copied"


def read_link_reports(site: Path | None) -> dict[str, dict]:
    if not site:
        return {}
    path = site / LINK_REPORT_NAME
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        family: upgrade_link_report(report)
        for family, report in data.get("families", {}).items()
    }


def empty_link_counts() -> dict:
    return {
        "document_links": {"exact": 0, "repaired": 0, "missing": 0, "ambiguous": 0},
        "navigation_links": {"exact": 0, "repaired": 0, "missing": 0, "ambiguous": 0},
        "placeholders": 0,
        "omitted_images": {"occurrences": 0, "targets": 0},
    }


def upgrade_link_report(report: dict) -> dict:
    counts = report.get("counts", {})
    if "document_links" in counts:
        return report
    old_placeholders = report.get("placeholders", [])
    placeholder_occurrences = sum(
        len(item.get("referring_pages", [])) for item in old_placeholders
    )
    upgraded_placeholders = [
        {
            "target": item.get("target", ""),
            "referrers": [
                {"kind": "document", "path": path}
                for path in item.get("referring_pages", [])
            ],
        }
        for item in old_placeholders
    ]
    return {
        "family": report.get("family", ""),
        "counts": {
            "document_links": {
                "exact": counts.get("exact", 0),
                "repaired": counts.get("repaired", 0),
                "missing": placeholder_occurrences or counts.get("placeholder", 0),
                "ambiguous": counts.get("ambiguous", 0),
            },
            "navigation_links": {
                "exact": 0,
                "repaired": 0,
                "missing": 0,
                "ambiguous": 0,
            },
            "placeholders": counts.get("placeholder", len(upgraded_placeholders)),
            "omitted_images": {"occurrences": 0, "targets": 0},
        },
        "repairs": [
            {"kind": "document", **repair}
            for repair in report.get("repairs", [])
        ],
        "placeholders": upgraded_placeholders,
        "omitted_images": [],
        "legacy_schema": 1,
    }


def empty_link_report(family: str) -> dict:
    return {
        "family": family,
        "counts": empty_link_counts(),
        "repairs": [],
        "placeholders": [],
        "omitted_images": [],
    }


def build_site(
    settings: Settings, output: Path, work: Path, previous_site: Path | None = None,
    source_repository: SourceRepository | None = None, discovery_result: Discovery | None = None,
    *, build_profile: str = "production", cleanup_work: bool = False,
) -> tuple[dict, bool]:
    if build_profile not in {"production", "smoke"}:
        raise ValueError(f"unsupported build profile: {build_profile}")
    source_repository = source_repository or RemoteSource()
    discovery = discovery_result or discover(settings, source_repository)
    if build_profile == "smoke":
        discovery = Discovery(
            families=[discovery.latest],
            latest=discovery.latest,
            publications=discovery.publications,
            shas={discovery.latest: discovery.shas[discovery.latest]},
        )
    previous = read_manifest(previous_site)
    previous_link_reports = read_link_reports(previous_site)
    fingerprint = pipeline_fingerprint(settings.root)
    previous_families = previous.get("families", {})
    previous_profile = previous.get("build_profile", "production")
    force_all = (
        previous.get("pipeline_fingerprint") != fingerprint
        or previous_profile != build_profile
    )
    changed = force_all or previous.get("latest") != discovery.latest
    output.mkdir(parents=True, exist_ok=True)
    family_records: dict[str, dict] = {}
    family_link_reports: dict[str, dict] = {}

    for family in discovery.families:
        sha = discovery.shas[family]
        old = previous_families.get(family, {})
        can_reuse = not force_all and old.get("source_sha") == sha and previous_site and (previous_site / family).is_dir()
        if can_reuse:
            method = copy_reused_family(previous_site / family, output / family)
            print(f"Build [{family}] reused previous output ({method})")
            family_link_reports[family] = previous_link_reports.get(family, empty_link_report(family))
        else:
            try:
                family_link_reports[family] = build_family(
                    settings,
                    discovery,
                    family,
                    work,
                    output,
                    source_repository,
                    search=build_profile == "production",
                )
            finally:
                if cleanup_work and (work / family).exists():
                    shutil.rmtree(work / family)
                    print(f"Build [{family}] workspace removed")
            changed = True
        family_records[family] = {
            "source_sha": sha,
            "archived": False,
            "path": f"/{family}/",
            "link_counts": family_link_reports[family]["counts"],
        }

    archived_families = previous_families.items() if build_profile == "production" else ()
    for family, record in archived_families:
        if family in family_records or not previous_site or not (previous_site / family).is_dir():
            continue
        method = copy_reused_family(previous_site / family, output / family)
        print(f"Build [{family}] retained archived output ({method})")
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
    aggregate_link_report = {"schema_version": 2, "families": family_link_reports}
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
        "build_profile": build_profile,
        "latest": discovery.latest,
        "families": family_records,
    }
    (output / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for family, report in family_link_reports.items():
        counts = report["counts"]
        documents = counts["document_links"]
        navigation = counts["navigation_links"]
        images = counts["omitted_images"]
        print(
            f"Normalization [{family}]: documents {documents['exact']} exact, "
            f"{documents['repaired']} repaired, {documents['missing']} missing; navigation "
            f"{navigation['exact']} exact, {navigation['repaired']} repaired, "
            f"{navigation['missing']} missing; {counts['placeholders']} placeholders; "
            f"{images['occurrences']} omitted images ({images['targets']} targets)"
        )
    return manifest, changed
