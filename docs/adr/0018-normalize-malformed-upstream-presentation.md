# ADR-0018: Normalize malformed upstream presentation structures

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** Victor Bilgin
- **Related commit:** `Normalize malformed upstream presentation` (intended subject)

## Context

The Australia source family contains repeatable presentation defects that remain valid enough for strict MkDocs rendering but expose Markdown syntax, duplicate navigation, malformed cards, broken code-fence boundaries, and overflowing content in the generated site. The defects occur in upstream-shaped raw HTML tables, publication indexes, and metadata, so repairing generated HTML would be disposable and would violate ADR-0017.

The UI audit also reported Markdown examples and Material navigation behavior that resemble defects but are intentional. Treating every observation as a release gate encouraged broad transformations and repeated family builds without establishing that zero findings was an appropriate acceptance condition.

## Decision

Normalize only recognized malformed upstream presentation structures during transformation. Render Markdown inside ordinary raw and nested HTML table cells, repair local table links through the family resolver, separate malformed fenced-code markers onto block boundaries, and recover known linked, split-link, missing-alt-marker, and informational navigation-card variants. Preserve unrecognized structures unchanged and protect explicit code content from prose transformations.

Normalize recognized Markdown escapes in page-title metadata and publication navigation. After link resolution, retain the first navigation occurrence of a destination and remove later occurrences, including redundant self-children, because Material canonicalizes repeated destinations to one page title.

Apply shared responsive containment to tables, code blocks, long inline values, links, and deeply nested mobile lists. Refine structural and Chromium detectors to ignore Markdown syntax inside explicit code examples, intentional Material navigation overflow, fixed controls, and content inside responsive horizontal scrollers.

Keep UI findings report-only. Use family builds and audits as review evidence, but do not require a zero-finding audit unless a later decision defines a specific gating policy.

## Consequences

- Repeatable upstream defects receive deterministic, source-level recovery with upstream-shaped regression fixtures.
- Ordinary table links participate in existing clean-URL rewriting, link repair, and reporting.
- Navigation exposes one stable entry per resolved destination; later contextual labels for the same destination are intentionally omitted.
- Long content remains available through wrapping or local scrolling instead of widening or clipping the page.
- Audit observations are more representative but remain heuristic and may include issues outside the current remediation scope.
- Transformation and theme changes alter the package fingerprint and require current families to rebuild before release.

## Alternatives considered

- **Patch generated HTML:** Rejected because generated output is disposable and source provenance would be obscured.
- **Run a general HTML repair pass:** Rejected because unfamiliar upstream structures must remain unchanged.
- **Keep every duplicate navigation label:** Rejected because Material renders one canonical page title and repeated destinations produced misleading visible duplicates.
- **Require zero UI findings:** Rejected because the audit is diagnostic, includes heuristic observations, and has no accepted release-gating policy.

## Related decisions

- [ADR-0003](0003-mkdocs-material-content-processing.md) defines light deterministic enrichment of upstream content.
- [ADR-0004](0004-stale-link-resolution.md) defines deterministic link repair and reporting.
- [ADR-0015](0015-local-hybrid-ui-audit.md) keeps UI auditing local and report-only.
- [ADR-0017](0017-remediate-ui-findings-at-source.md) requires remediation at the earliest responsible source layer.
