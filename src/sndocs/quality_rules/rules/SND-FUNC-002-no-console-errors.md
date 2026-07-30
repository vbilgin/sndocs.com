---
id: SND-FUNC-002
title: Audited pages should not log console errors
status: active
category: function
severity: warning
assessment: manual
references: []
tags:
  - browser
  - console
  - diagnostics
---

# Audited pages should not log console errors

## Requirement

Audited pages should not emit browser console messages at error level.

## Rationale

Console errors frequently reveal broken resources, invalid state, or degraded functionality before a visible failure is reported.

## Applicability

This rule applies to pages opened locally with `sndocs serve` during manual review.

## Passing Examples

```text
No error-level console messages.
```

## Failing Examples

```text
Failed to initialize search worker.
```

## Evaluation

This rule has no automated browser detector; assess it manually by opening representative pages with `sndocs serve` and checking the browser console for error-level messages as part of the preview checklist before promotion.

## Limitations

Third-party browser behavior can occasionally produce messages unrelated to a site defect, so findings require review. Manual assessment covers only the pages reviewed during the checklist, not the full site.

## Remediation

Trace the message to its source and correct the responsible theme, script, configuration, or resource.

## References

This is a project-specific diagnostic requirement.
