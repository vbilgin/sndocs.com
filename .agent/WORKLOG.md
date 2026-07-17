# Work Log

Reverse-chronological record of significant project work. This is a historical index, not the source of truth for implementation details; consult `.agent/CONTEXT.md`, ADRs, the current code, tests, and Git history as appropriate.

## 2026-07-17 — Override an ambiguous Australia formatter link

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** Pending

### Outcome

Allowed the Australia family build to resolve one reviewed upstream ambiguity while preserving fatal behavior for every unrecognized ambiguous stale link.

### Changes and decisions

- Added an override keyed by family, referring page, and original target for the stale Approval summarizer formatter link.
- Selected the `servicenow-platform/approvals/` destination based on its administrative canonical location and breadcrumb.
- Required override destinations to exist and recorded successful use as `explicit-override` in the link report.
- Added ADR-0007 to supersede and narrowly extend ADR-0004's strict ambiguity policy.

### Verification

- Full test suite: 21 passed, 1 filesystem-specific skip.
- `git diff --check` passed.

## 2026-07-16 — Establish layered agent context

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `docs: establish layered project context and agent guidance`

### Outcome

Established the first part of a layered, repository-backed context system intended to help future agents resume work without loading full conversation histories.

### Changes

- Added `.agent/CONTEXT.md` as the compact primary handoff document.
- Recorded the project objective, current architecture, invariants, artifact contract, implementation status, known risks, next work, and verification commands.
- Chose `.agent/WORKLOG.md` for recent historical context and `docs/adr/` for durable architectural decisions.
- Added an indexed initial ADR set covering the upstream source contract, version lifecycle, content processing, stale-link repair, release artifacts, and layered context maintenance.
- Added root `AGENTS.md` with repository-wide context-loading, development, verification, documentation-maintenance, ADR, Git, and handoff policies.
- Defined Git history as the authoritative source for exact changes and authorship.

### Decisions

- Keep `CONTEXT.md` deliberately bounded and update it as current state changes.
- Keep the worklog reverse chronological and consult it selectively rather than loading it automatically in full.
- Archive older worklog entries when the active file becomes large.
- Use root `AGENTS.md` to tell future agents how to consume and maintain these files.

### Verification

- Cross-checked the context summary against current source files and recent commits.
- Validated the root agent policy's referenced paths, context/worklog size thresholds, Markdown source formatting, and whitespace.
- Test suite: 19 passed, 1 skipped on a case-insensitive macOS filesystem.

### Follow-up


## 2026-07-16 — Resolve stale upstream documentation links

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `32e6f14` — `fix: resolve stale upstream documentation links`

### Outcome

Prevented stale ServiceNowDocs paths from producing large numbers of MkDocs warnings and broken local links while preserving strict failure behavior for ambiguous repairs.

### Changes

- Added a family-aware Markdown inventory and deterministic link resolver.
- Preserved exact targets, repaired globally unique basename moves, and used the stated publication to disambiguate duplicate basenames.
- Added fatal errors containing the source page and candidates when ambiguity remains.
- Generated diagnostic placeholder pages when an upstream target does not exist.
- Added `link-report.json` with per-family repairs and missing-target references.
- Added link-resolution counts to `build-manifest.json` and retained reports across incremental and archived builds.
- Extended artifact validation to check report/manifest consistency.
- Excluded generated Python bytecode from the pipeline fingerprint.

### Investigation and decisions

- Traced a representative stale Hermes link to an upstream file move from `servicenow-platform/hermes-messaging-service.md` to `servicenow-platform/multi-instance-framework-hermes/hermes-messaging-service.md`.
- An Australia scan found 398 stale-link occurrences across 111 target paths: 391 were deterministically repairable and 7 occurrences represented 3 genuinely missing targets.
- Chose automatic deterministic repair, placeholders for missing targets, and aggregate reporting instead of per-page warning floods.
- Left cross-family moved-link resolution out of scope because family directory structures can differ.

### Verification

- Resolver, ambiguity, placeholder, report, incremental-reuse, artifact, and strict MkDocs fixture tests passed.
- Final test suite at commit time: 19 passed, 1 filesystem-specific skip.

### Follow-up

- Validate the resolver during a complete multi-family build.
- Inspect the resulting report and placeholder pages in the assembled site.

## 2026-07-16 — Tolerate malformed upstream YAML frontmatter

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `3a728fd` — `fix: tolerate malformed YAML in upstream frontmatter`

### Outcome

Allowed the site build to continue when ServiceNowDocs frontmatter contains an unquoted colon in a scalar value such as a page title.

### Changes

- Kept strict PyYAML parsing for valid frontmatter.
- Added a conservative field-by-field fallback for malformed upstream YAML.
- Preserved scalar titles and descriptions while continuing to decode valid lists, dates, and numbers.
- Added a regression test reproducing the reported malformed title.

### Verification

- The original YAML scanner failure was reproduced from build output and covered by a test.
- Test suite after the fix: 11 passed, 1 filesystem-specific skip.

### Follow-up

- Continue treating malformed source data as recoverable only when field boundaries remain unambiguous.

## 2026-07-16 — Implement ServiceNowDocs-to-MkDocs pipeline

- **Work performed by:** Codex, with requirements and decisions from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `dbc74ff` — `feat: add ServiceNowDocs-to-MkDocs build pipeline`

### Outcome

Created the initial end-to-end Python pipeline for producing a versioned MkDocs Material mirror from the public `ServiceNow/ServiceNowDocs` repository.

### Changes

- Added the `sndocs` Python package and `discover`, `build`, `validate`, and `package` CLI commands.
- Parsed upstream `llms.txt` to discover ordered release families and publications.
- Added shallow family cloning, publication-index navigation generation, Markdown transformation, metadata enrichment, raw-link rewriting, omitted-image notices, and empty-file placeholders.
- Built each family independently under `/<family>/` and redirected the artifact root to the newest family.
- Added SHA-based incremental reuse and retention of deleted families as archived output.
- Added MkDocs Material search, styling, attribution, non-affiliation messaging, and a `versions.json`-driven family selector.
- Added artifact manifests, ServiceNow license preservation, ZIP/TAR packaging, and SHA-256 checksums.
- Added a scheduled/manual GitHub Actions workflow that publishes a rolling GitHub Release only when upstream SHAs or pipeline inputs change.
- Added pinned dependencies, project documentation, unit tests, and a strict MkDocs fixture.

### Decisions

- Publish all families declared by `llms.txt` and make the newest the default.
- Retain removed families rather than mirroring upstream deletion.
- Use family subpaths and host-agnostic GitHub Release artifacts.
- Preserve source prose with light enrichment.
- Use Material's client-side search initially.
- Keep generated Markdown and HTML out of the main branch.
- Brand the site as an independent `sndocs.com` community mirror with ServiceNow attribution and Apache-2.0 notices.

### Verification

- Live discovery confirmed Australia, Zurich, Yokohama, and Xanadu and resolved their branch SHAs.
- Unit tests, strict MkDocs fixture build, archive parity/checksum tests, workflow YAML parsing, bytecode compilation, and wheel creation passed.

### Follow-up

- Complete and inspect the first full multi-family site build.
- Validate navigation usability, search performance, artifact size, and release automation.

## 2026-07-16 — Initialize repository

- **Work performed by:** Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `1c9df9d` — `Initial commit`

### Outcome

Created the `sndocs.com` repository with an MIT license and initial README, establishing the workspace for the documentation pipeline.
