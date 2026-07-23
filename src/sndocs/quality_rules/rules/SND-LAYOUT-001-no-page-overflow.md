---
id: SND-LAYOUT-001
title: Pages must not overflow the viewport horizontally
status: active
category: layout
severity: error
assessment: automated
references: []
tags:
  - responsive
  - overflow
  - viewport
---

# Pages must not overflow the viewport horizontally

## Requirement

The rendered document width must not exceed the configured viewport width beyond the audit tolerance.

## Rationale

Page-level horizontal scrolling makes navigation and reading difficult, especially on mobile devices.

## Applicability

This rule applies at every audited desktop and mobile viewport.

## Passing Examples

```text
document width = viewport width
```

## Failing Examples

```text
document width = 900px; mobile viewport = 390px
```

## Evaluation

Chromium compares the document element's scroll width and client width with a small rounding tolerance.

## Limitations

Components intentionally offering their own bounded horizontal scrolling do not necessarily violate this page-level rule.

## Remediation

Make the responsible content responsive or contain its scrolling within an accessible component.

## References

This rule supports responsive reflow but is not itself a claim of WCAG conformance.
