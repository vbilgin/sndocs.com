# ADR-0004: Repair deterministic stale links and preserve missing targets

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owner:** Victor Bilgin
- **Related commit:** `32e6f14` — `fix: resolve stale upstream documentation links`

## Context

The upstream repository contains absolute raw-GitHub links that sometimes retain an old path after the target document moves. A scan of the Australia family found 398 stale-link occurrences across 111 declared targets: 391 occurrences were deterministically repairable, while 7 occurrences referred to 3 targets absent from the branch.

Faithfully converting a stale absolute URL into a relative URL produces a broken local link and repetitive MkDocs warnings. Blind fuzzy matching could silently link readers to the wrong topic.

## Decision

Build a case-sensitive Markdown inventory for each family and resolve same-family targets in this order:

1. Preserve the declared path when it exists.
2. Use the only case-insensitive basename match when globally unique.
3. When the basename has multiple matches, use the only candidate in the target's stated publication.
4. Fail before MkDocs when multiple plausible candidates remain.
5. When no candidate exists, retain the requested route and generate one clearly marked placeholder page listing its referring documents.

Do not attempt cross-family moved-link repair because the target family's directory layout is not available to the current per-family transformation pass and can differ independently.

Record repairs and placeholders in `link-report.json`, summarize counts in `build-manifest.json`, retain reports during incremental and archived-family reuse, and print one aggregate console summary per family.

## Consequences

- Most upstream folder moves are repaired without manual mappings or warning floods.
- Ambiguous matches fail visibly instead of creating plausible but incorrect links.
- Truly missing documents preserve navigation continuity while clearly disclosing the upstream absence.
- Reports make every automatic repair auditable.
- Cross-family links may remain stale when a target moves within another family.

## Alternatives considered

- **Preserve all stale upstream paths:** Rejected because it knowingly publishes broken links.
- **Maintain only curated path overrides:** Rejected as the default because it requires ongoing manual maintenance for hundreds of predictable moves.
- **Use unrestricted fuzzy matching:** Rejected because similar filenames and topics can produce semantically incorrect links.
- **Render missing links as plain text:** Rejected because placeholders better preserve navigation context and explain the source defect.
- **Infer an official ServiceNow URL for missing files:** Rejected because a reliable canonical target is not always available.
