# Project Context

Compact current-state handoff; use `.agent/WORKLOG.md`, ADRs, and Git history for historical detail.

## Objective

Build an independent versioned MkDocs mirror of `ServiceNow/ServiceNowDocs`.

## Current architecture

- `pipeline.toml` defines site identity, upstream source, family selection, and artifact naming.
- `discovery.py` parses upstream `llms.txt`, preserves its family/publication ordering, and resolves release-branch SHAs.
- `source.py` provides remote and reusable-local sources; local sources export exact family commits from clean remote-tracking refs without changing branches.
- `navigation.py` converts publication `index.md` hierarchies into MkDocs navigation and resolves their targets through the shared family link resolver.
- `transform.py` tolerates malformed YAML frontmatter, enriches pages, rewrites links, converts recognized upstream navigation tables into responsive linked cards, renders missing local images as omitted-image notices, and creates placeholders for unavailable content.
- Raw HTML tables receive deterministic recovery for embedded Markdown, nesting, malformed fences, and recognized card variants; unfamiliar structures remain unchanged.
- `links.py` repairs stale same-family document and navigation links using exact paths, unique basenames, same-publication disambiguation, self-canonical metadata, and narrowly scoped reviewed fallback overrides; unresolved ambiguity is fatal.
- `builder.py` builds families independently, fingerprints settings and package contents, reuses output, retains archives, and assembles manifests.
- `artifacts.py` validates the assembled site and creates ZIP/TAR archives with SHA-256 checksums.
- `quality.py` validates packaged Markdown quality rules and detector registration; `ui_audit.py` applies them through full-tree structural scanning and sampled Chromium rendering.
- `.github/workflows/build-site.yml` runs scheduled or manual builds and publishes the rolling `site-artifact` GitHub Release when inputs change.

The `sndocs` 0.2 CLI manages the pipeline; optional `audit-ui` and `quality` commands expose report-only audits and human-readable rules.

## Important invariants and decisions

- Upstream `llms.txt` is authoritative for current families and publication ordering.
- Every current family is published under `/<family>/`; the root redirects to the newest.
- Deleted upstream families remain available as immutable archived snapshots.
- Publication indexes define navigation, but all Markdown files are rendered so inbound links remain valid; expected omitted-navigation listings are suppressed without weakening strict validation.
- Same-family moved links are repaired when the destination is deterministic through path or self-canonical metadata, or selected by a family/source/target-specific reviewed fallback override.
- Navigation and page titles shed Markdown escapes; navigation retains the first resolved destination because Material canonicalizes duplicate destinations.
- Missing upstream targets receive clearly marked diagnostic placeholder pages.
- Cross-family moved-link resolution is intentionally not attempted.
- MkDocs strict mode remains enabled; ambiguity and pipeline-created broken links fail.
- Production builds include every selected family and search; smoke manifests are distinct, omit search, and cannot be packaged.
- Existing output requires explicit `--clean` replacement; dry runs never write or delete files.
- Automatic workspaces below the invocation directory's `.temp/` are config-independent and cleaned automatically; explicit `--work-dir` content is preserved.
- Source prose is preserved with light enrichment rather than editorial restructuring.
- Upstream media is not restored because ServiceNowDocs intentionally omits it.
- Generated Markdown and HTML stay out of the main branch.
- Topics use host-agnostic directory URLs (`/topic/` backed by `topic/index.html`); preview them over HTTP.
- Mirrored content retains required trademark, UTC build-year copyright, and Apache-2.0 notices plus an independent-site disclaimer and upstream link.

## Artifact contract

The assembled site contains:

- one directory for each current or archived family;
- `index.html` redirecting to the newest family;
- `versions.json` for the release selector;
- `build-manifest.json` with source SHAs, archive state, build profile, pipeline fingerprint, and link counts;
- schema-version-2 `link-report.json` with typed document/navigation repairs, missing-document placeholders, and omitted-image occurrences; and
- `SERVICENOW-LICENSE.txt`.

Packaging produces `sndocs-site.tar.gz`, `sndocs-site.zip`, and SHA-256 files for both.

## Current status

- Production navigation prunes inactive branches, family sites no longer have a duplicate temporary copy, and local source archives stream during extraction.
- The test suite reports 123 passing tests and one filesystem-specific skip on case-insensitive macOS.
- Australia SHA `0dfa6b2` passed the final strict diagnostic render in 243.74 seconds with only 20 known informational stale-anchor messages.
- Production and smoke builds minify HTML while leaving inline JavaScript and CSS untouched; Australia output shrank by 46.4% in validation.
- Every family receives a Material landing page, and artifact validation rejects missing family roots or unrewritten current-family raw Markdown links.
- Recognized upstream `nav-card` tables render as accessible adaptive card grids with clean directory links and descriptions recovered from omitted-icon alt text.
- UI remediation covers table Markdown, fences, card variants, title and navigation normalization, responsive containment, and detector precision.
- The UI audit groups evidence under 10 semantic rules and has a documented triage, regression-fixture, and family-level rebuild workflow; report paths cannot overlap the read-only input site.
- The retained final Australia audit scanned 49,089 HTML pages, rendered 143 selected pages at both viewports, recorded 9 grouped findings without audit errors, and remains diagnostic rather than a zero-finding gate.

## Known gaps and risks

- GitHub Actions publication to the rolling Release has not yet been proven in production.
- Full families remain large; Australia has roughly 49,000 pages and generates 4.03 GiB.
- Navigation usability and Material search performance still need browser evaluation against a successful complete site.
- Australia contains 20 stale-anchor diagnostics at MkDocs' informational level; anchor validation intentionally remains informational.
- Cross-family links can still become stale when equivalent topics move between directories in different release branches.
- The remediation changes have not received a complete current-family production build; retained Australia output is a family-only smoke diagnostic and is not packageable.
- The final Australia report still identifies visible Markdown, escapes, duplicate navigation, overflow, unresolved local links, and one page error for manual review or separately scoped remediation.

## Next likely work

1. Review the retained Australia diagnostic site and UI report; scope any follow-up findings independently rather than treating zero findings as an implicit gate.
2. Rebuild every current family through the normal production fingerprint flow and measure artifact and search performance.
3. Verify rolling Release reuse and publication.

Use the README virtual-environment workflow and `upstream.families` for local restrictions. Repository state remains authoritative.
