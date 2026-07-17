# ADR-0003: Generate a lightly enriched MkDocs Material site

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owner:** Victor Bilgin
- **Related commits:** `dbc74ff`, `3a728fd`

## Context

The upstream repository is optimized for LLM consumption rather than direct human browsing. It contains Markdown and useful frontmatter but omits media, uses absolute raw-GitHub links, occasionally publishes empty files, and has included malformed YAML such as unquoted colons in scalar titles.

The mirror should improve human navigation without editorially rewriting ServiceNow's documentation or implying that `sndocs.com` is an official ServiceNow property.

## Decision

Use MkDocs with the Material theme to generate the static site. Enable Material's built-in client-side English search, responsive navigation, previous/next navigation, code highlighting, and a custom release selector.

Preserve source prose and headings while applying light deterministic enrichment: retain useful frontmatter, add release/update metadata and breadcrumbs, link to the official canonical page and GitHub source, convert same-family raw Markdown links to local links, and style omitted-image annotations as notices.

Do not attempt to restore upstream media. Generate a diagnostic page for an upstream file that exists but is empty. Parse valid frontmatter strictly; when upstream YAML is malformed, use a conservative known-field fallback that preserves unambiguous values.

Keep MkDocs strict mode enabled so pipeline-created navigation and link errors remain visible. Identify the site as an independent community mirror, retain ServiceNow attribution and Apache-2.0 notices, and avoid official-looking ServiceNow branding.

## Consequences

- The generated site is useful to human readers while remaining recognizably derived from the source.
- Content changes remain reproducible and reviewable because transformations are deterministic.
- Missing images remain a known limitation and are disclosed rather than silently hidden.
- Client-side search may become large enough to affect browser performance and must be measured against complete builds.
- Tolerant frontmatter recovery prevents isolated upstream formatting defects from aborting an otherwise valid build.

## Alternatives considered

- **Copy Markdown nearly verbatim:** Rejected because raw links, sparse metadata presentation, and omitted-image markers provide a poor browsing experience.
- **Editorially restructure or rewrite pages:** Rejected because it would create maintenance burden and risk changing source meaning.
- **Fetch media from servicenow.com:** Rejected because media is intentionally absent from the source repository and the official site is not the pipeline's source contract.
- **Disable strict builds:** Rejected because it would conceal pipeline regressions.
- **Operate an external search service initially:** Deferred until client-side search performance is measured.
