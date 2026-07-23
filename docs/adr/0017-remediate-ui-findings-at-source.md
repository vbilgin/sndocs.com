# ADR-0017: Remediate UI findings at their source layer

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** Victor Bilgin
- **Related commit:** `Protect UI audits from overlapping output paths` (intended subject)

## Context

The local UI audit reports structural and browser-rendered defects in generated family sites. Contributors need a consistent way to turn those observations into corrections without making generated output authoritative, obscuring upstream meaning, or leaving navigation, search, shared assets, and neighboring pages stale. A production family contains tens of thousands of pages, so diagnostic iteration must also remain practical.

## Decision

Triage every audit observation before changing production behavior. Correct confirmed defects at the earliest responsible transformation, link-resolution, navigation, theme, configuration, or assembly layer. Handle repeatable malformed upstream structures only through narrow deterministic normalization with an upstream-shaped regression fixture. Correct detector false positives or browser-environment failures without changing generated content.

Keep `audit-ui` report-only and independent from the build path. Its report directory must not equal, contain, or be contained by the audited site, including when `--clean` is used. Do not patch generated Markdown or HTML and do not add a generic post-build repair phase.

Treat one complete release family as the smallest safe rendering unit. Use a one-family smoke build for routine transformation, navigation, and layout diagnosis. Use an isolated one-family production build when search or production-only assets matter, but do not package that diagnostic output. After accepting a rendering-pipeline correction, build every current family for release under the existing package-wide pipeline fingerprint and retain archived families unchanged.

## Consequences

- Fixes remain deterministic, reviewable, testable, and reproducible from upstream inputs.
- Audit results guide source fixtures and owning-layer changes rather than becoming mutation instructions.
- Diagnostic family builds shorten iteration while complete release builds preserve cross-page and shared-output consistency.
- Page-level rebuild optimization remains unavailable until a dependency model covers navigation, search, shared assets, placeholders, and adjacent-page behavior.
- Audit-only detector changes can be checked against an existing site even though a later package-wide pipeline fingerprint change may rebuild current families.

## Alternatives considered

- **Patch affected generated files:** Rejected because generated output is disposable and later builds would discard the correction.
- **Add an automatic post-build repair phase:** Rejected because it would duplicate owning-layer logic and obscure provenance.
- **Rebuild only reported pages:** Rejected because MkDocs output has family-wide navigation, search, asset, and neighboring-page dependencies.
- **Always use complete production builds while diagnosing:** Rejected because the cost is disproportionate before a correction has been validated.

## Related decisions

- [ADR-0002](0002-versioned-families-and-archive-retention.md) defines complete families as independent incremental build units.
- [ADR-0010](0010-bound-build-workspaces-and-smoke-profile.md) defines smoke-build behavior.
- [ADR-0015](0015-local-hybrid-ui-audit.md) keeps UI auditing local and report-only.
- [ADR-0016](0016-versioned-site-quality-ruleset.md) defines stable semantic rules and detector registration.
