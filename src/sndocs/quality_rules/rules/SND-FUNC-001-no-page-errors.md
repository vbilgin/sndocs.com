---
id: SND-FUNC-001
title: Audited pages must not raise browser page errors
status: active
category: function
severity: error
assessment: automated
references: []
tags:
  - browser
  - javascript
  - runtime
---

# Audited pages must not raise browser page errors

## Requirement

Rendering and interacting with an audited page must not raise an uncaught browser page error.

## Rationale

Uncaught errors can disable search, navigation, release selection, or other required behavior.

## Applicability

This rule applies during local Chromium rendering of selected pages.

## Passing Examples

```text
No pageerror events.
```

## Failing Examples

```text
ReferenceError: missingValue is not defined
```

## Evaluation

The browser detector records uncaught `pageerror` events during page loading and inspection.

## Limitations

Only code paths exercised by the audit are observed.

## Remediation

Correct the generated script, asset loading, or theme integration that raised the error.

## References

This is a project-specific functional requirement.
