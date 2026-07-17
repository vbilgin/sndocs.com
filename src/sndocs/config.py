from __future__ import annotations

import tomllib
from pathlib import Path

from .models import Settings


def load_settings(path: Path) -> Settings:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    site = data["site"]
    upstream = data["upstream"]
    build = data.get("build", {})
    return Settings(
        root=path.parent.resolve(),
        site_name=site.get("name", "sndocs.com"),
        site_url=site.get("url", "").rstrip("/"),
        site_description=site.get("description", ""),
        repository=upstream.get("repository", "ServiceNow/ServiceNowDocs"),
        llms_path=upstream.get("llms_path", "llms.txt"),
        family_allowlist=tuple(upstream.get("families", [])),
        archive_basename=build.get("archive_basename", "sndocs-site"),
    )
