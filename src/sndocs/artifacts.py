from __future__ import annotations

import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path


def validate_site(site: Path) -> None:
    manifest = json.loads((site / "build-manifest.json").read_text(encoding="utf-8"))
    versions = json.loads((site / "versions.json").read_text(encoding="utf-8"))
    link_report = json.loads((site / "link-report.json").read_text(encoding="utf-8"))
    if link_report.get("schema_version") != 2:
        raise ValueError("link-report.json must use schema version 2")
    if versions["latest"] != manifest["latest"]:
        raise ValueError("manifest and versions.json disagree about the latest family")
    for family in manifest["families"]:
        if not (site / family / "index.html").exists():
            raise ValueError(f"family {family} has no generated index.html")
        reported = link_report.get("families", {}).get(family)
        if not reported:
            raise ValueError(f"family {family} has no link-resolution report")
        expected_counts = manifest["families"][family].get("link_counts")
        if expected_counts is not None and expected_counts != reported.get("counts"):
            raise ValueError(f"family {family} link counts disagree between manifest and report")
        counts = reported.get("counts", {})
        if not {"document_links", "navigation_links", "placeholders", "omitted_images"} <= counts.keys():
            raise ValueError(f"family {family} has an incomplete schema-v2 link report")
    current_families = set(manifest["families"])
    raw_link = re.compile(r"raw\.githubusercontent\.com/ServiceNow/ServiceNowDocs/([^/]+)/markdown/")
    for html_file in site.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8", errors="replace")
        if any(match.group(1) in current_families for match in raw_link.finditer(text)):
            raise ValueError(f"unrewritten upstream Markdown link in {html_file.relative_to(site)}")


def _files(site: Path):
    return sorted(path for path in site.rglob("*") if path.is_file())


def package_site(site: Path, destination: Path, basename: str) -> list[Path]:
    manifest = json.loads((site / "build-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("build_profile", "production") != "production":
        raise ValueError("smoke builds cannot be packaged as production artifacts")
    validate_site(site)
    destination.mkdir(parents=True, exist_ok=True)
    tar_path = destination / f"{basename}.tar.gz"
    zip_path = destination / f"{basename}.zip"
    with tarfile.open(tar_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in _files(site):
            archive.add(path, arcname=path.relative_to(site).as_posix(), recursive=False)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _files(site):
            archive.write(path, path.relative_to(site).as_posix())
    archives = [tar_path, zip_path]
    outputs = list(archives)
    for path in archives:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum = path.with_suffix(path.suffix + ".sha256")
        checksum.write_text(f"{digest}  {path.name}\n", encoding="ascii")
        outputs.append(checksum)
    return outputs
