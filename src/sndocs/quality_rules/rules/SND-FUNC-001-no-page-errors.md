---
id: SND-FUNC-001
title: Audited pages must not raise browser page errors
status: active
category: function
severity: error
assessment: manual
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

This rule applies to pages opened locally with `sndocs serve` during manual review.

## Passing Examples

```text
No pageerror events.
```

## Failing Examples

```text
ReferenceError: missingValue is not defined
```

## Evaluation

This rule has no automated browser detector; assess it manually by opening representative pages with `sndocs serve` and checking the browser console for uncaught errors as part of the preview checklist before promotion.

## Limitations

Only code paths exercised during manual review are observed.

## Remediation

Correct the generated script, asset loading, or theme integration that raised the error.

## References

This is a project-specific functional requirement.
