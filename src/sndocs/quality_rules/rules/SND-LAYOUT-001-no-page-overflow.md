---
id: SND-LAYOUT-001
title: Pages must not overflow the viewport horizontally
status: active
category: layout
severity: error
assessment: manual
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

This rule has no automated browser detector; assess it manually with `sndocs serve` at representative desktop and mobile widths as part of the preview checklist before promotion.

## Limitations

Components intentionally offering their own bounded horizontal scrolling do not necessarily violate this page-level rule. Manual assessment covers only the pages reviewed during the checklist, not the full site.

## Remediation

Make the responsible content responsive or contain its scrolling within an accessible component.

## References

This rule supports responsive reflow but is not itself a claim of WCAG conformance.
