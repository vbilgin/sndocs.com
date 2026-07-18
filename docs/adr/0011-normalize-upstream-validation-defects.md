# ADR-0011: Normalize deterministic upstream validation defects before strict builds

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decision owner:** Victor Bilgin
- **Related commit:** Pending

## Context

An Australia production build at upstream SHA `71f4936517ebd1fbaf76c5515c40b8d12bc6dd5c` transformed all content without ambiguity but MkDocs strict mode rejected 494 warning-level upstream defects: 488 stale publication-index paths and 6 references to 3 image files absent from the repository. A render-free audit confirmed that stale anchors were not part of the strict failure; MkDocs reports 20 of them at its default informational level. The existing document-link resolver could deterministically repair every stale navigation occurrence, while genuinely missing navigation targets already followed the project's placeholder policy.

## Decision

Use one family link resolver for document links and publication-index navigation. Apply the established exact-path, unique-basename, same-publication, self-canonical, and reviewed-override rules to both reference kinds, retain fatal ambiguity behavior, and finalize diagnostic placeholders only after both passes have contributed missing targets.

Convert conventional Markdown image references to missing local assets into accessible omitted-image notices while preserving the filename and alternative text. Do not transform Markdown-looking text inside raw HTML containers, which MkDocs does not parse as images, and do not fetch or fabricate omitted media.

Keep MkDocs strict mode and its validation levels unchanged. Publish typed document, navigation, placeholder, and omitted-image details in schema version 2 of `link-report.json`; convert retained schema-version-1 reports for archived families when assembling a new artifact.

## Consequences

- Stale upstream navigation retains its hierarchy and reaches the deterministic current page instead of failing or publishing a dead route.
- Missing documents and images remain explicit to readers and auditable without weakening strict validation for new defects.
- Content and navigation repairs share the same resolution policy and ambiguity safeguards.
- The report schema is intentionally incompatible with version 1, so retained archived reports require deterministic conversion.
- Warning normalization does not reduce the generated site or search-index size.

## Alternatives considered

- **Allowlist warning fingerprints by family SHA:** Rejected because it would publish known dead navigation and image references and require continuing baseline maintenance.
- **Downgrade MkDocs missing-target validation:** Rejected because it would hide future pipeline-created regressions.
- **Drop invalid navigation entries:** Rejected because most rejected paths have deterministic current destinations and publication indexes remain authoritative for hierarchy.
- **Generate placeholders for every stale navigation path:** Rejected because placeholders are reserved for genuinely unavailable targets.
- **Wait for upstream corrections:** Rejected as the only strategy because historical snapshots must remain reproducibly buildable.
