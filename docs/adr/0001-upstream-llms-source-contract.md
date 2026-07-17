# ADR-0001: Treat upstream llms.txt as the source contract

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owner:** Victor Bilgin
- **Related commit:** `dbc74ff` — `feat: add ServiceNowDocs-to-MkDocs build pipeline`

## Context

`ServiceNow/ServiceNowDocs` is organized by release-family branches rather than as one evergreen documentation tree. Its root `llms.txt` documents the current family-to-branch mapping, identifies the newest family, orders publications, and links to each publication's `index.md`. ServiceNow updates the repository regularly and removes the oldest family branch as new families reach general availability.

The pipeline needs an upstream contract that can be discovered automatically without scraping the JavaScript-based official documentation site or maintaining a duplicate publication list locally.

## Decision

Treat upstream `llms.txt` as authoritative for the set and order of current release families, the newest family, and top-level publication ordering. Resolve each declared branch's Git SHA and use SHA changes as the content-change signal.

Treat each publication's `markdown/<publication>/index.md` as authoritative for its nested navigation hierarchy. Render every Markdown file in the branch even when it is absent from navigation so inbound and cross-publication links can still resolve.

Allow an optional configured family allowlist for local experiments, but default production builds to every family declared by `llms.txt`.

## Consequences

- The site follows upstream release and publication changes without a manually maintained catalog.
- A malformed or incompatible `llms.txt` causes discovery to fail visibly instead of silently publishing incomplete content.
- The pipeline remains dependent on ServiceNow preserving the documented `llms.txt` and publication-index conventions.
- Files outside navigation remain buildable and searchable, increasing artifact and search-index size.

## Alternatives considered

- **Maintain families and publications in local configuration:** Rejected because it duplicates frequently changing upstream metadata and risks drift.
- **Scrape servicenow.com/docs:** Rejected because the official site is a JavaScript application and the source repository explicitly directs automated consumers to its Markdown.
- **Build only files listed by publication indexes:** Rejected because valid inbound links may target unlisted documents.
