---
id: SND-LINK-002
title: Generated local link targets must exist
status: active
category: link
severity: error
assessment: automated
references: []
tags:
  - links
  - integrity
  - generated-site
---

# Generated local link targets must exist

## Requirement

Every checkable local anchor destination must resolve to a file or clean directory route in the assembled site.

## Rationale

Missing local targets interrupt documentation tasks and indicate a failed rewrite, omission, or assembly step.

## Applicability

This rule applies to generated-site navigation and content links. External URLs, fragments, application `.do` examples, templates, and non-site payload examples are excluded.

## Passing Examples

```html
<a href="../existing-topic/">Existing topic</a>
```

## Failing Examples

```html
<a href="../absent-topic/">Absent topic</a>
```

## Evaluation

Static inspection normalizes each applicable local URL and checks it against the complete assembled-site file set.

## Limitations

Application-relative examples require explicit exclusion because they are not destinations within sndocs.com.

## Remediation

Repair the link deterministically, generate an auditable placeholder when policy permits, or correct the assembled output.

## References

See ADR-0011 for deterministic link repair and missing-target policy.
