# ADR-0009: Resolve stale links using canonical metadata before overrides

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decision owner:** Victor Bilgin
- **Supersedes:** [ADR-0007](0007-explicit-stale-link-overrides.md)
- **Related commit:** `33abe28` — `Resolve stale links using canonical metadata`

## Context

ADR-0007 permits reviewed source-specific overrides when duplicate basenames make a stale link ambiguous. A later Australia build exposed many stale links to a Source-to-Pay glossary whose intended destination was identifiable from upstream metadata, but adding another override would only repair one family, referring page, and target tuple. Repeating that approach would grow a manual exception table for defects that carry deterministic identity evidence.

## Decision

Index each candidate document's `canonical_url` and treat it as self-canonical only when an official `www.servicenow.com/docs/r/` URL normalizes exactly to that candidate's repository-relative Markdown path. Normalize URL encoding, upstream Markdown escapes, and the `.html` suffix conservatively.

After exact-path, unique-basename, and unique-same-publication resolution, select a destination when exactly one applicable candidate is self-canonical. Record the repair method as `self-canonical`. This rule is independent of family, referring page, and original stale target, so previously unseen links can use the same deterministic evidence.

Retain reviewed overrides only after deterministic rules fail. If canonical metadata is missing, invalid, or shared by multiple candidates, use a matching override or fail visibly. Do not score titles, products, classifications, or breadcrumbs.

## Consequences

- Canonical identity repairs recurring and previously unseen stale-link patterns without per-link configuration.
- Multiple self-canonical candidates remain ambiguous, preserving strict failure unless a reviewed override exists.
- Frontmatter parsing is shared by transformation and link inventory so malformed upstream YAML receives consistent treatment.
- Resolver initialization performs a bounded frontmatter read for each Markdown file.
- Explicit overrides remain necessary for semantic choices such as the Approval summarizer formatter, whose two candidates are both self-canonical.

## Alternatives considered

- **Continue adding overrides:** Rejected as the default because it does not generalize across referring pages or new defects.
- **Score all metadata fields:** Rejected because metadata presence and breadcrumb similarity are not reliable identity assertions.
- **Remove overrides entirely:** Rejected because canonical metadata can remain tied even when review establishes the intended destination.
- **Accept any canonical URL:** Rejected because external hosts and non-matching paths do not prove a candidate's repository identity.
