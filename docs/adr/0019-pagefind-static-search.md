# ADR-0019: Use chunked Pagefind search for current families

- **Status:** Accepted
- **Date:** 2026-07-28
- **Decision owner:** Victor Bilgin
- **Related commit:** `b41ea68` — `Replace monolithic search with Pagefind`
- **Supersedes:** The built-in-search portion of [ADR-0003](0003-mkdocs-material-content-processing.md)

## Context

Material's built-in search sends one JSON document to the browser and constructs a Lunr index in a web worker. The retained Australia production family generated a 222 MiB index with 248,730 page and section records. The worker could eventually initialize, but ordinary queries stalled while searching, highlighting, and grouping the oversized in-memory index.

The site must retain family-scoped full-text search without adding a hosted service, credentials, telemetry, or deployment-specific server behavior. Search output must remain compatible with the host-agnostic static artifact and immutable archived-family policy.

## Decision

Build a Pagefind 1.x index after rendering each current production family. Limit indexing to the rendered article container, force English indexing, and emit Pagefind's compressed metadata, fragment, and index chunks inside that family's output. Do not enable Material's search plugin or generate `search/search_index.json`.

Render Pagefind's accessible modal trigger in the Material header only for production builds. Resolve the bundle relative to the generated component script and derive the result base path at runtime from MkDocs' page-relative family root, so nested pages and installations below a URL prefix remain valid. Theme the components with the established sndocs.com palette.

Keep smoke builds search-free. Rebuild current families when the Pagefind version changes, validate their required Pagefind files, and preserve archived family trees byte-for-byte even when they contain the legacy Material search implementation.

## Consequences

- Browsers load small query-relevant chunks instead of downloading and indexing the complete family corpus.
- Search remains fully static, family-scoped, and independent of the preview or production web server.
- Production builds gain a pinned platform-specific Pagefind binary and a post-render indexing phase.
- Theme integration now includes a version-sensitive Material header override that must be checked during Material upgrades.
- Archived families may retain an older search experience until they have previously been rebuilt as a current family.

## Alternatives considered

- **Retain full Material search:** Rejected because the measured Australia index is not operationally usable.
- **Index titles only:** Rejected because body-text search is required.
- **Operate a hosted search service:** Rejected because it adds runtime infrastructure, credentials, and deployment coupling.
- **Rewrite Material's worker around Pagefind:** Rejected because Pagefind's maintained accessible components provide a smaller and more supportable integration.
