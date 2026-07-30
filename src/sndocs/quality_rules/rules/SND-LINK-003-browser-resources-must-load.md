---
id: SND-LINK-003
title: Browser resources must load successfully
status: active
category: link
severity: error
assessment: manual
references: []
tags:
  - browser
  - resources
  - network
---

# Browser resources must load successfully

## Requirement

Resources requested while rendering an audited page must not fail or return an HTTP error response.

## Rationale

Missing scripts, stylesheets, fonts, and images can break layout, interaction, branding, or content.

## Applicability

This rule applies to requests initiated while browsing pages locally with `sndocs serve` during manual review.

## Passing Examples

```text
200 /assets/stylesheets/main.css
```

## Failing Examples

```text
404 /assets/stylesheets/missing.css
```

## Evaluation

This rule has no automated browser detector; assess it manually with `sndocs serve` and the browser network panel, confirming representative pages load with no failed request or response of 400 or greater, as part of the preview checklist before promotion.

## Limitations

Manual assessment observes only resources requested by the pages reviewed during the checklist, not the full site.

## Remediation

Restore or correct the resource reference and ensure it is included in generated output.

## References

This is a project-specific functional integrity requirement.
