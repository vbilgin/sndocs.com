# ADR-0024: Validate generated UI without a browser

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owner:** Victor Bilgin
- **Supersedes:** [ADR-0015](0015-local-hybrid-ui-audit.md) in full

## Context

ADR-0015 established `sndocs audit-ui` as a hybrid scanner: a deterministic static pass over every generated HTML file, plus Chromium rendering of a deduplicated high-risk sample and a seeded additional sample, using Playwright. That browser layer backed 8 of the 14 registered detectors and the only detector for five quality rules (`SND-LAYOUT-001`, `SND-LAYOUT-002`, `SND-FUNC-001`, `SND-FUNC-002`, `SND-LINK-003`) — page overflow, clipped components, uncaught page errors, console errors, and failed browser resource loads. `scripts/verify_deployment.py`'s optional `--browser` acceptance check used the same dependency, though the publication workflow never actually passed `--browser`, making that code path already dead in practice.

Removing GitHub Actions (ADR-0023) removes the only environment that reliably had Playwright's Chromium runtime pre-provisioned. Keeping browser-based validation would mean either provisioning it by hand on the operator's own machine before every audit, or accepting that the audit silently degrades. Separately, the project's stated near-term priority is rewriting the Markdown-to-HTML transform layer itself; adding an unrelated browser-provisioning dependency to that work is exactly the kind of complexity this round of changes is meant to remove.

`quality.py` raises when an active rule with `assessment: automated` has no registered detector. Removing the eight `browser.*` detectors without also changing rule status therefore breaks `sndocs quality *` and `structural_audit` outright — the ruleset would no longer load.

## Decision

Remove Playwright as a dependency. Delete `ui_audit.browser_audit` and everything that existed only to support it: page sampling (`select_pages`), screenshot naming and viewport constants, and the report fields that were always `None` without a browser (`viewport`, `screenshot`, `browser_renders`, `high_risk_pages`, `configuration.viewports`, `errors`). `sndocs audit-ui` becomes a static-only structural scan: it reads every generated HTML file and reports findings from the six detectors that were always regex-based static analysis (`static.visible-markdown-link`, `static.suspicious-link-label`, `static.visible-markdown-escape`, `static.duplicate-navigation-entry`, `static.raw-markdown-destination`, `static.missing-local-target`). It remains report-only and continues to reject an output path that overlaps its input site.

For the five rules that lose their only detector, change `assessment: active` rules' `assessment` field from `automated` to `manual`, keeping `status: active`. This is deliberately not a `status` change to `deprecated` or `retired`: the requirements these rules describe — no page overflow, no clipped tables, no uncaught errors, no console errors, no failed resource loads — remain real and remain policy. They move to the "active rules not automatically evaluated" section of the audit report, and their `## Evaluation` and `## Limitations` sections are rewritten to describe the manual check: opening representative pages with `sndocs serve` at desktop and mobile widths as part of the preview checklist before promotion, rather than an automated Chromium pass over a sampled page set.

Remove `scripts/verify_deployment.py`'s `check_browser` and its `--browser` flag along with it; its stdlib-only `check_http` — release-header, range-request, and 404 checks — is unaffected and remains the automated part of deployment verification.

The report schema advances to `schema_version: 3`, dropping the now-always-empty browser-only fields rather than keeping them as vestigial `null`s. This is a diagnostic report, not part of the packaged artifact contract, so the version bump has no build-output consequence.

## Consequences

- `sndocs audit-ui` requires no browser installation and runs in seconds rather than minutes, at the cost of losing automated detection of viewport overflow, clipped tables, uncaught JavaScript errors, console errors, and failed resource loads.
- The five affected rules stay visible as active policy in every audit report, explicitly marked as requiring manual assessment rather than silently dropped.
- The manual preview checklist in the deployment runbook is now the only check for those five requirements before a release is promoted; `publish_cli.promote` requires `--i-reviewed-preview` and prints that checklist, but nothing enforces that the operator actually performed it.
- CONTEXT.md previously recorded an intent to "restore a scoped browser gate after two successful releases and the observation period." That intent is withdrawn, not deferred: this decision replaces the browser gate with permanent manual assessment rather than a temporary rollout measure.
- Reintroducing automated coverage for these five rules in the future is a new decision, not a reversion — the ADR-0015 rationale (bounded Chromium cost via deduplication and sampling) is retained here for reference but is no longer the operative design.

## Alternatives considered

- **Keep Playwright behind an optional extra, unused by default:** Rejected — an unused optional dependency with no scheduled provisioning path degrades silently rather than failing loudly, and the five rules it backs would still read as "automated" without ever actually running.
- **Retire the five affected rules instead of demoting their assessment:** Rejected — the underlying defect classes (overflow, clipping, script errors) are real risks the project has hit before (see `.agent/WORKLOG.md`, 2026-07-22); demoting to `manual` keeps them as visible policy instead of deleting the record that they matter.
- **Demote `status` to `deprecated` instead of `assessment` to `manual`:** Rejected — `quality.py` gates its "no detector" failure on `status == "active" and assessment == "automated"` together; changing `status` would additionally and unnecessarily drop the rules from `catalog(active_only=True)`, which is not the intended effect.
- **Replace Chromium with a lighter headless renderer:** Deferred — no lighter option was found that preserves the same detector fidelity, and the priority is removing browser dependence now, not substituting one.

## Related decisions

- [ADR-0015](0015-local-hybrid-ui-audit.md) is fully superseded by this decision.
- [ADR-0016](0016-versioned-site-quality-ruleset.md) and [ADR-0017](0017-remediate-ui-findings-at-source.md) define the ruleset and remediation workflow this decision operates within; neither is superseded.
- [ADR-0023](0023-publish-from-a-local-operator-workstation.md) removes the CI environment that made browser provisioning free.
- [Deployment runbook](../deployment-runbook.md) documents the manual preview checklist that now covers these five rules.
