---
id: SND-LAYOUT-002
title: Content components must not be unintentionally clipped
status: active
category: layout
severity: warning
assessment: manual
references: []
tags:
  - tables
  - navigation
  - overflow
---

# Content components must not be unintentionally clipped

## Requirement

Visible tables, navigation regions, and primary content containers must not hide content through unintended horizontal overflow.

## Rationale

Clipping can make table columns, links, and prose inaccessible even when the overall page width remains bounded.

## Applicability

This rule applies to visible audited table, navigation, and content containers.

## Passing Examples

```text
scroll width is no greater than client width
```

## Failing Examples

```text
table scroll width = 900px; table client width = 320px without an intentional scroll treatment
```

## Evaluation

This rule has no automated browser detector; assess it manually with `sndocs serve`, inspecting representative tables and navigation regions at desktop and mobile widths as part of the preview checklist before promotion.

## Limitations

Some accessible responsive tables intentionally scroll, so findings require review. Manual assessment covers only the pages reviewed during the checklist, not the full site.

## Remediation

Use responsive table presentation, wrapping, or an explicit accessible scrolling container.

## References

This is a project-specific layout-quality requirement.
