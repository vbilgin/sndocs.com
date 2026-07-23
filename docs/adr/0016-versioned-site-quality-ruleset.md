# ADR-0016: Define site quality with packaged Markdown rules

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** Victor Bilgin
- **Related commit:** `Pending`

## Context

The initial local UI audit encoded detector names, severity, messages, and grouping directly in Python. Static and browser checks for the same defect appeared as unrelated findings, and contributors had no durable human-readable definition of what constituted acceptable generated documentation.

## Decision

Make one strict Markdown file per stable semantic quality rule the normative source for requirement, applicability, severity, assessment, examples, limitations, and remediation. Package the rules with `sndocs`, validate their lifecycle and required prose, and derive a deterministic digest rather than maintaining a manual ruleset version.

Keep executable behavior in a registered Python detector identified separately from its rule. Each detector declares phase and confidence; the rule owns impact severity. Active automated rules require detectors, while active assisted and manual rules may remain unevaluated.

Publish UI findings with report schema version 2, grouped by semantic rule with detector observations and affected-page unions. Include ruleset schema, package version, digest, and the active catalog in every report. Version-1 UI reports are local generated artifacts and are not upgraded.

Provide read-only `sndocs quality validate`, `list`, and `show` commands. Keep detected defects report-only and retain local-only audit execution.

## Consequences

- Contributors can evolve requirements through reviewable Markdown without duplicating executable logic.
- Static and browser evidence for one requirement share a stable rule identity.
- Severity and detector confidence communicate different dimensions and can support future gating policy.
- Invalid packaged rules or detector mappings prevent an audit from starting.
- Rule files and schema changes become installed package inputs and require wheel-content coverage.

## Alternatives considered

- **One YAML catalog:** Rejected because extended rationale, examples, and remediation are awkward to author and review.
- **Hard-coded Python definitions:** Rejected because they are not an approachable or durable contributor-facing quality specification.
- **Separate prose and machine catalogs:** Rejected because duplicated sources would drift.
- **Manual ruleset version:** Rejected in favor of schema version, package version, and a content digest.
