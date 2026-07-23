---
id: SND-RENDER-001
title: Markdown link syntax must not appear as visible text
status: active
category: render
severity: error
assessment: automated
references: []
tags:
  - markdown
  - source-conversion
  - tables
---

# Markdown link syntax must not appear as visible text

## Requirement

Generated page content and link labels must render Markdown links as anchors rather than exposing their source syntax.

## Rationale

Visible Markdown is difficult to read, produces unusable destinations, and shows that source conversion lost document meaning.

## Applicability

This rule applies to visible generated page content and navigation. Intentional Markdown examples inside code elements are excluded.

## Passing Examples

```html
<a href="../target/">Target</a>
```

## Failing Examples

```text
[Target](target.md)
```

## Evaluation

Static inspection identifies Markdown-shaped visible text and suspicious link labels; browser inspection confirms text exposed in the rendered page.

## Limitations

Detection must distinguish documentation about Markdown from malformed converted content.

## Remediation

Repair the deterministic source transformation so the original label and destination become a valid anchor.

## References

This is a project-specific render-integrity requirement.
