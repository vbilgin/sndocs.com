---
id: SND-NAV-001
title: Navigation siblings must not contain duplicate entries
status: active
category: navigation
severity: warning
assessment: automated
references: []
tags:
  - navigation
  - hierarchy
  - duplicates
---

# Navigation siblings must not contain duplicate entries

## Requirement

A visible navigation group must not repeat the same normalized label and destination among its entries.

## Rationale

Duplicates obscure hierarchy, waste navigation space, and make the generated information architecture appear unreliable.

## Applicability

This rule applies within each visible navigation group. Legitimate repeated links in separate navigation regions are excluded.

## Passing Examples

```text
Create a password
Reset a password
```

## Failing Examples

```text
Password Reset reports
Password Reset reports
```

## Evaluation

Static inspection identifies repeated label-and-target pairs and browser inspection confirms duplicate visible siblings.

## Limitations

Static markup can contain responsive navigation copies, so browser confirmation has higher confidence.

## Remediation

Deduplicate the authoritative publication navigation without discarding distinct destinations that happen to share a title.

## References

This is a project-specific navigation-integrity requirement.
