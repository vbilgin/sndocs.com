# ADR-0014: Suppress expected omitted-navigation diagnostics

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** Victor Bilgin
- **Related commit:** `Pending`

## Context

Publication indexes define the visible MkDocs navigation, but the artifact intentionally renders every upstream Markdown file so direct and inbound links remain valid. MkDocs consequently reports every rendered page absent from the explicit navigation configuration. Complete families contain tens of thousands of such pages, so this expected informational list can exhaust terminal history and obscure useful build progress and diagnostics.

## Decision

Set MkDocs `validation.nav.omitted_files` to `ignore` in generated family configurations. Continue rendering pages omitted from navigation, keep strict mode enabled, and leave every other navigation, link, and anchor validation level unchanged.

## Consequences

- Builds no longer print the expected per-file omitted-navigation list.
- Publication indexes remain authoritative for visible navigation while all Markdown remains renderable and searchable.
- Genuine broken links and other warning-level validation failures remain visible and fatal under strict mode.

## Alternatives considered

- **Run MkDocs with `--quiet`:** Rejected because it would suppress unrelated warnings and useful diagnostics globally.
- **Add every rendered page to navigation:** Rejected because it would replace the upstream publication hierarchy with an impractically large menu.
- **Retain the informational list:** Rejected because its volume obscures actionable output without adding audit value.

## Related decisions

- [ADR-0001](0001-upstream-llms-source-contract.md) requires rendering all upstream Markdown, including files absent from publication indexes.
- [ADR-0003](0003-mkdocs-material-content-processing.md) establishes strict MkDocs validation.
- [ADR-0011](0011-normalize-upstream-validation-defects.md) keeps actionable validation levels unchanged while normalizing deterministic upstream defects.
