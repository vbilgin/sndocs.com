from __future__ import annotations

import posixpath
from collections import defaultdict
from pathlib import Path, PurePosixPath


class AmbiguousLinkError(ValueError):
    """Raised when a stale target has more than one plausible destination."""


def normalize_path(value: str) -> PurePosixPath:
    normalized = posixpath.normpath(value)
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        raise ValueError(f"unsafe documentation target: {value}")
    return PurePosixPath(normalized)


class FamilyLinkResolver:
    def __init__(self, source_markdown: Path, family: str):
        self.family = family
        self.paths = {
            PurePosixPath(path.relative_to(source_markdown).as_posix())
            for path in source_markdown.rglob("*.md")
        }
        self.by_basename: dict[str, list[PurePosixPath]] = defaultdict(list)
        for path in sorted(self.paths, key=str):
            self.by_basename[path.name.casefold()].append(path)
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

