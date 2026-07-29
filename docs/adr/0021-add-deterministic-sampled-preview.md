# ADR-0021: Add a deterministic sampled preview

- **Status:** Accepted
- **Date:** 2026-07-28
- **Decision owner:** Victor Bilgin
- **Related commit:** Pending — `Add fast sampled preview command`

## Context

A complete Australia family currently contains 48,989 Markdown files and takes several minutes to transform and render. The existing smoke profile avoids search indexing but intentionally retains complete-family transformation and rendering, so it remains too slow for a quick check of the generated theme, representative content, navigation, version assembly, and search experience. The supported `serve` command also requires a separate completed build.

Sampled output cannot preserve every family-wide dependency. Publication navigation, topic links, search, placeholders, shared assets, and neighboring pages make a complete family the smallest safe unit for exhaustive diagnosis and release validation. A fast preview therefore needs a visibly distinct contract that remains deterministic, strict, auditable, and non-packageable.

## Decision

Add `sndocs preview` as a combined sampled build, validation, and local-server workflow. It honors every family selected by configuration or repeatable `--family`, requires explicit output replacement through `--clean`, includes Pagefind, binds to `127.0.0.1` on an available port by default, reports the allocated URL, and retains output after interruption. It does not open a browser and does not support JSON output, dry runs, smoke mode, incremental reuse, or production packaging.

For each family, group Markdown by its top-level source directory. Include that area's `index.md`, the first valid topic declared by the index, and one additional topic selected by a stable SHA-256 ordering of its source path. Areas without a usable index select up to two topics through the same stable ordering. Render only those files while copying non-Markdown assets, generate sampled navigation and a complete coverage page, and place an incomplete-preview warning on transformed pages and generated landings.

Keep links between selected same-family topics local. Convert links to existing but omitted topics, including cross-family topics, into human-readable GitHub blob links. Preserve the existing repair and placeholder policy for genuinely absent same-family targets. Record the strategy identifier, source and selected Markdown counts, source-area count, selected-topic count, and externalized-link count in optional preview-only family manifest metadata.

Treat `preview` as a third build profile. Preview requires the same Pagefind artifact validation as production, retains no archived families, and is incompatible with production and smoke reuse. It is a rapid sanity check only; complete-family smoke and production builds remain the validation units for exhaustive behavior and release artifacts.

## Consequences

- Contributors can inspect a representative, searchable multi-family site after rendering only a tiny fraction of each source tree.
- Sampling is stable across filesystem enumeration and covers small source areas that a global random sample could miss.
- Preview navigation and omitted-topic links intentionally differ from production, and the UI discloses that difference.
- Exact source materialization still occurs before sampling, so remote clone or local archive time remains part of the command.
- The preview profile extends manifests compatibly through optional metadata but cannot enter production packaging or reuse flows.

## Alternatives considered

- **Make smoke sampled:** Rejected because smoke is an accepted complete-family strict-validation profile.
- **Add a blocking flag to `build`:** Rejected because a dedicated long-running command makes automatic serving explicit.
- **Use a global random sample:** Rejected because large publications would dominate and small source areas could receive no coverage.
- **Generate local placeholders for every omitted topic:** Rejected because publication indexes reference tens of thousands of topics and would recreate much of the full build.
- **Disable strict validation:** Rejected because sampled navigation and link behavior can remain internally consistent without weakening MkDocs.

## Related decisions

- [ADR-0010](0010-bound-build-workspaces-and-smoke-profile.md) defines complete-family smoke behavior.
- [ADR-0012](0012-clean-directory-urls-and-local-preview.md) defines the supported local HTTP server.
- [ADR-0013](0013-simplify-and-harden-cli.md) defines output replacement, profile, and CLI reporting contracts.
- [ADR-0017](0017-remediate-ui-findings-at-source.md) retains complete families as the safe unit for exhaustive diagnosis.
- [ADR-0019](0019-pagefind-static-search.md) defines production-style static search.
