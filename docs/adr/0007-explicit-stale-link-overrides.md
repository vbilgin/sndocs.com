# ADR-0007: Permit narrowly scoped explicit stale-link overrides

- **Status:** Superseded by [ADR-0009](0009-canonical-metadata-link-resolution.md)
- **Date:** 2026-07-17
- **Decision owner:** Victor Bilgin
- **Supersedes:** [ADR-0004](0004-stale-link-resolution.md)
- **Related commit:** Pending

## Context

ADR-0004 requires unresolved stale-link ambiguity to fail rather than silently select a plausible destination. A complete Australia build exposed an upstream link from `platform-administration/c_Formatters.md` to the removed `platform-administration/r_ApprovalSummarizerFormatter.md`. Two current documents share that basename, under `build-workflows/approvals/` and `servicenow-platform/approvals/`, so the general resolver cannot choose safely.

The `servicenow-platform` document is the intended administrative successor based on its canonical location and breadcrumb, but that conclusion is a reviewed exception rather than a generally applicable inference rule.

## Decision

Retain the resolution order and strict ambiguity failure from ADR-0004, but permit source-controlled overrides keyed by release family, referring page, and original target. Apply an override only after confirming the declared target is stale and require its destination to exist in the current family inventory. Record its repair method as `explicit-override` in `link-report.json`.

Add one override for the Australia formatter link and resolve it to `servicenow-platform/approvals/r_ApprovalSummarizerFormatter.md`. All other ambiguous links remain fatal.

## Consequences

- Reviewed upstream defects can be handled without weakening general ambiguity detection.
- Overrides are deterministic, release-specific, source-specific, visible in code, and auditable in build reports.
- Upstream changes that remove an override destination fail visibly.
- Curated exceptions require occasional maintenance and review.

## Alternatives considered

- **Choose the first basename match:** Rejected because repository traversal or lexical order is not semantic evidence.
- **Prefer `servicenow-platform` globally:** Rejected because that rule could misroute unrelated duplicate topics.
- **Generate a placeholder for ambiguity:** Rejected because the reviewed successor is known and a placeholder would unnecessarily interrupt navigation.
- **Patch the downloaded upstream Markdown:** Rejected because transformations should remain explicit and attributable without mutating the source checkout.
