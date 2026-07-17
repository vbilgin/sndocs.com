# ADR-0002: Publish versioned release families and retain archives

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owner:** Victor Bilgin
- **Related commit:** `dbc74ff` — `feat: add ServiceNowDocs-to-MkDocs build pipeline`

## Context

ServiceNow documentation changes across release families, and upstream retains only the most recent families. Users need to know which release a page describes, while links to older documentation should remain stable after upstream deletes a branch.

Building all families on every refresh would also be expensive because each branch contains tens of thousands of Markdown files.

## Decision

Publish each current family under a stable `/<family>/` path and redirect the artifact root to the newest family declared by `llms.txt`. Expose all current and archived families through `versions.json` and the site release selector.

Build families independently. Compare upstream branch SHAs and the pipeline fingerprint with the preceding manifest, reuse unchanged generated family output, and rebuild only changed or newly discovered families.

When a family disappears upstream, retain its last successfully generated output as an immutable archived version and mark it archived in version metadata and the build manifest.

## Consequences

- URLs communicate release context and remain stable across upstream release turnover.
- Removed upstream families remain available without requiring their deleted source branches.
- Incremental builds avoid repeatedly processing unchanged families.
- The previous assembled artifact becomes required state for reuse and archive retention.
- Pipeline changes intentionally invalidate the fingerprint and rebuild current families.

## Alternatives considered

- **Publish only the newest family:** Rejected because users support instances on multiple releases and need version-specific documentation.
- **Delete families when upstream deletes them:** Rejected because it would break stable historical URLs.
- **Use the newest family at the root and older families under subpaths:** Rejected because root URLs would change meaning between releases.
- **Rebuild every family on every run:** Rejected because of unnecessary cloning and build cost.
