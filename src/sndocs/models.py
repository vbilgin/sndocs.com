from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Publication:
    name: str
    slug: str
    index_url: str


@dataclass
class Discovery:
    families: list[str]
    latest: str
    publications: list[Publication]
    shas: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "families": self.families,
            "latest": self.latest,
            "publications": [asdict(item) for item in self.publications],
            "shas": self.shas,
        }


@dataclass(frozen=True)
class Settings:
    root: Path
    site_name: str
    site_url: str
    site_description: str
    repository: str
    llms_path: str
    family_allowlist: tuple[str, ...]
    archive_basename: str

