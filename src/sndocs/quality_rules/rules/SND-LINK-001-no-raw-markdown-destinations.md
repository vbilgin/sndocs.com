---
id: SND-LINK-001
title: Generated local links must not target Markdown files
status: active
category: link
severity: error
assessment: automated
references: []
tags:
  - links
  - markdown
  - clean-urls
---

# Generated local links must not target Markdown files

## Requirement

Local links in generated pages must target rendered site routes rather than `.md` source files.

## Rationale

Markdown files are not part of the published site contract and lead readers to missing or incorrectly served resources.

## Applicability

This rule applies to local destinations. Explicit external source-repository links are excluded.

## Passing Examples

```html
<a href="../target/">Target</a>
```

## Failing Examples

```html
<a href="../target.md">Target</a>
```

## Evaluation

Static inspection parses local anchor destinations and reports paths whose document component ends in `.md`.

## Limitations

None for conventional local anchors; dynamically constructed example URLs are outside the generated-site contract.

## Remediation

Resolve and rewrite the source Markdown destination to its clean generated directory URL.

## References

See ADR-0012 for the clean directory-URL contract.
