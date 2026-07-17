from __future__ import annotations

import posixpath
from collections import defaultdict
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from .metadata import read_frontmatter


class AmbiguousLinkError(ValueError):
    """Raised when a stale target has more than one plausible destination."""


LINK_OVERRIDES: dict[tuple[str, PurePosixPath, PurePosixPath], PurePosixPath] = {
    (
        "australia",
        PurePosixPath("platform-administration/c_Formatters.md"),
        PurePosixPath("platform-administration/r_ApprovalSummarizerFormatter.md"),
    ): PurePosixPath("servicenow-platform/approvals/r_ApprovalSummarizerFormatter.md"),
}


def normalize_path(value: str) -> PurePosixPath:
    normalized = posixpath.normpath(value)
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        raise ValueError(f"unsafe documentation target: {value}")
    return PurePosixPath(normalized)


def canonical_source_path(value: object) -> PurePosixPath | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value.replace("\\", ""))
        official_host = parsed.hostname == "www.servicenow.com"
    except ValueError:
        return None
    if not official_host or not parsed.path.startswith("/docs/r/"):
        return None
    canonical = unquote(parsed.path.removeprefix("/docs/r/"))
    if not canonical.endswith(".html"):
        return None
    try:
        return normalize_path(canonical.removesuffix(".html") + ".md")
    except ValueError:
        return None


class FamilyLinkResolver:
    def __init__(self, source_markdown: Path, family: str):
        self.family = family
        self.paths = {
            PurePosixPath(path.relative_to(source_markdown).as_posix())
            for path in source_markdown.rglob("*.md")
        }
        self.by_basename: dict[str, list[PurePosixPath]] = defaultdict(list)
        self.self_canonical: set[PurePosixPath] = set()
        for path in sorted(self.paths, key=str):
            self.by_basename[path.name.casefold()].append(path)
            metadata = read_frontmatter(source_markdown / Path(path.as_posix()))
            if canonical_source_path(metadata.get("canonical_url")) == path:
                self.self_canonical.add(path)
        self.exact = 0
        self.repairs: list[dict[str, str]] = []
        self.missing: dict[PurePosixPath, set[PurePosixPath]] = defaultdict(set)

    def resolve(self, target_value: str, referring_page: PurePosixPath) -> PurePosixPath:
        target = normalize_path(target_value)
        if target in self.paths:
            self.exact += 1
            return target

        candidates = self.by_basename.get(target.name.casefold(), [])
        if len(candidates) == 1:
            return self._repair(target, candidates[0], referring_page, "unique-basename")

        if len(candidates) > 1:
            same_publication = [candidate for candidate in candidates if candidate.parts[0] == target.parts[0]]
            if len(same_publication) == 1:
                return self._repair(target, same_publication[0], referring_page, "same-publication")
            canonical_pool = same_publication or candidates
            self_canonical = [candidate for candidate in canonical_pool if candidate in self.self_canonical]
            if len(self_canonical) == 1:
                return self._repair(target, self_canonical[0], referring_page, "self-canonical")

        override = LINK_OVERRIDES.get((self.family, referring_page, target))
        if override is not None:
            if override not in self.paths:
                raise ValueError(
                    f"stale link override target does not exist in {self.family}: {override}"
                )
            return self._repair(target, override, referring_page, "explicit-override")

        if len(candidates) > 1:
            choices = ", ".join(str(item) for item in candidates)
            raise AmbiguousLinkError(
                f"ambiguous stale link in {referring_page}: {target}; candidates: {choices}"
            )

        self.missing[target].add(referring_page)
        return target

    def _repair(
        self,
        original: PurePosixPath,
        resolved: PurePosixPath,
        referring_page: PurePosixPath,
        method: str,
    ) -> PurePosixPath:
        self.repairs.append(
            {
                "source": str(referring_page),
                "original": str(original),
                "resolved": str(resolved),
                "method": method,
            }
        )
        return resolved

    def report(self) -> dict:
        placeholders = [
            {
                "target": str(target),
                "referring_pages": [str(item) for item in sorted(referrers, key=str)],
            }
            for target, referrers in sorted(self.missing.items(), key=lambda item: str(item[0]))
        ]
        return {
            "family": self.family,
            "counts": {
                "exact": self.exact,
                "repaired": len(self.repairs),
                "placeholder": len(placeholders),
                "ambiguous": 0,
            },
            "repairs": self.repairs,
            "placeholders": placeholders,
        }
