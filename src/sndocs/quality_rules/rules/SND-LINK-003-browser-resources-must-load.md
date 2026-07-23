---
id: SND-LINK-003
title: Browser resources must load successfully
status: active
category: link
severity: error
assessment: automated
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

This rule applies to requests initiated during local Chromium audit rendering.

## Passing Examples

```text
200 /assets/stylesheets/main.css
```

## Failing Examples

```text
404 /assets/stylesheets/missing.css
```

## Evaluation

The browser detector observes failed requests and responses with status codes of 400 or greater.

## Limitations

The audit observes only resources requested by selected pages and the configured browser state.

## Remediation

Restore or correct the resource reference and ensure it is included in generated output.

## References

This is a project-specific functional integrity requirement.
