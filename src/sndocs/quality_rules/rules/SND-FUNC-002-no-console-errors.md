---
id: SND-FUNC-002
title: Audited pages should not log console errors
status: active
category: function
severity: warning
assessment: automated
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

This rule applies during local Chromium rendering of selected pages.

## Passing Examples

```text
No error-level console messages.
```

## Failing Examples

```text
Failed to initialize search worker.
```

## Evaluation

The browser detector records console events whose level is `error`.

## Limitations

Third-party browser behavior can occasionally produce messages unrelated to a site defect, so findings require review.

## Remediation

Trace the message to its source and correct the responsible theme, script, configuration, or resource.

## References

This is a project-specific diagnostic requirement.
