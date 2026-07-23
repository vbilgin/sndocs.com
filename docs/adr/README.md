# Architecture Decision Records

This directory contains durable decisions that shape `sndocs.com`. ADRs explain why the project behaves as it does; `.agent/CONTEXT.md` summarizes current state, `.agent/WORKLOG.md` records chronological work, and Git history contains exact implementation details.

## Status values

- **Proposed:** Under consideration and not yet binding.
- **Accepted:** Current project policy.
- **Superseded:** Replaced by a later ADR, which must be linked from both records.
- **Deprecated:** Retained for history but no longer recommended.

Accepted ADRs are immutable except for corrections and explicit supersession metadata. Changes in direction should create a new ADR rather than rewriting the original rationale.

## Index

- [ADR-0001: Treat upstream llms.txt as the source contract](0001-upstream-llms-source-contract.md)
- [ADR-0002: Publish versioned release families and retain archives](0002-versioned-families-and-archive-retention.md)
- [ADR-0003: Generate a lightly enriched MkDocs Material site](0003-mkdocs-material-content-processing.md)
- [ADR-0004: Repair deterministic stale links and preserve missing targets](0004-stale-link-resolution.md)
- [ADR-0005: Publish host-agnostic rolling release artifacts](0005-host-agnostic-release-artifacts.md)
- [ADR-0006: Maintain layered repository context for agents and contributors](0006-layered-project-context.md)
- [ADR-0007: Permit narrowly scoped explicit stale-link overrides](0007-explicit-stale-link-overrides.md)
- [ADR-0008: Use reproducible local source snapshots for testing](0008-reproducible-local-source-snapshots.md)
- [ADR-0009: Resolve stale links using canonical metadata before overrides](0009-canonical-metadata-link-resolution.md)
- [ADR-0010: Bound build workspaces and distinguish smoke output](0010-bound-build-workspaces-and-smoke-profile.md)
- [ADR-0011: Normalize deterministic upstream validation defects before strict builds](0011-normalize-upstream-validation-defects.md)
- [ADR-0012: Preserve clean directory URLs and provide local HTTP preview](0012-clean-directory-urls-and-local-preview.md)
- [ADR-0013: Simplify and harden the public CLI](0013-simplify-and-harden-cli.md)
- [ADR-0014: Suppress expected omitted-navigation diagnostics](0014-suppress-omitted-navigation-diagnostics.md)
- [ADR-0015: Audit generated UI with a local hybrid scanner](0015-local-hybrid-ui-audit.md)
- [ADR-0016: Define site quality with packaged Markdown rules](0016-versioned-site-quality-ruleset.md)
- [ADR-0017: Remediate UI findings at their source layer](0017-remediate-ui-findings-at-source.md)
