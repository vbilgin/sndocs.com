---
id: SND-RENDER-002
title: Markdown escape syntax must not appear in navigation
status: active
category: render
severity: warning
assessment: automated
references: []
tags:
  - markdown
  - navigation
  - escaping
---

# Markdown escape syntax must not appear in navigation

## Requirement

Navigation labels must display their intended punctuation without Markdown escape backslashes.

## Rationale

Leaked escapes make labels look corrupted and expose source-format implementation details to readers.

## Applicability

This rule applies to visible navigation links. Literal backslashes that are meaningful parts of a label are excluded.

## Passing Examples

```text
Service instances (Application services)
```

## Failing Examples

```text
Service instances \(Application services\)
```

## Evaluation

Static and browser detectors inspect navigation labels for backslashes preceding Markdown punctuation.

## Limitations

The detector cannot always determine whether an unusual backslash is intentional, so findings require review.

## Remediation

Normalize the navigation title before passing it to MkDocs while preserving the underlying wording.

## References

This is a project-specific render-integrity requirement.
