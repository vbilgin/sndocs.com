# Project Context

Compact current-state handoff; use `.agent/WORKLOG.md`, ADRs, and Git history for historical detail.

## Objective

Build an independent versioned MkDocs mirror of `ServiceNow/ServiceNowDocs`.

## Current architecture

- `pipeline.toml` defines site and repository identity, upstream source, family selection, and artifact naming.
- `discovery.py` parses upstream `llms.txt`, preserves its family/publication ordering, and resolves release-branch SHAs.
- `source.py` provides remote and reusable-local sources; local sources export exact family commits from clean remote-tracking refs without changing branches.
- `navigation.py` converts publication `index.md` hierarchies into MkDocs navigation and resolves their targets through the shared family link resolver.
- `transform.py` recovers malformed frontmatter, enriches pages, rewrites links, converts recognized navigation tables into responsive cards, renders omitted-image notices, and creates placeholders.
- Raw HTML tables receive deterministic recovery for embedded Markdown, nesting, malformed fences, and recognized card variants; unfamiliar structures remain unchanged.
- `links.py` repairs stale same-family links using exact paths, unique basenames, publication context, self-canonical metadata, and reviewed overrides; unresolved ambiguity is fatal.
- `builder.py` builds and fingerprints families, creates family-scoped Pagefind indexes, reuses output, retains archives, and assembles manifests.
- `artifacts.py` validates the assembled site and creates ZIP/TAR archives with SHA-256 checksums.
- `quality.py` validates packaged quality rules and detector registration; `ui_audit.py` applies them through structural scanning and sampled Chromium rendering.
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
- Production builds include a static Pagefind full-text index in every selected current family; smoke manifests are distinct, omit search, and cannot be packaged.
- Generated UI uses the `sndocs` brand and an auto-hiding header linked to `vbilgin/sndocs.com`; `sndocs.com` remains the domain and `ServiceNow/ServiceNowDocs` remains the content source.
- Existing output requires explicit `--clean` replacement; dry runs never write or delete files.
- Automatic workspaces below the invocation directory's `.temp/` are config-independent and cleaned automatically; explicit `--work-dir` content is preserved.
- Source prose receives light enrichment rather than editorial restructuring; intentionally omitted upstream media is not restored.
- Generated Markdown and HTML stay out of the main branch.
- Topics use host-agnostic directory URLs (`/topic/` backed by `topic/index.html`); preview them over HTTP.
- Mirrored content retains required trademark, UTC build-year copyright, and Apache-2.0 notices plus an independent-site disclaimer and upstream link.

## Artifact contract

The assembled site contains:

- one directory for each current or archived family;
- a `pagefind/` search bundle inside each current production family;
- `index.html` redirecting to the newest family;
- `versions.json` for the release selector;
- `build-manifest.json` with source SHAs, archive state, build profile, pipeline fingerprint, and link counts;
- schema-version-2 `link-report.json` with typed document/navigation repairs, missing-document placeholders, and omitted-image occurrences; and
- `SERVICENOW-LICENSE.txt`.

Packaging produces `sndocs-site.tar.gz`, `sndocs-site.zip`, and SHA-256 files for both.

## Current status

- Production navigation prunes inactive branches, family sites avoid duplicate temporary copies, and local source archives stream during extraction.
- Current families use Pagefind's query-loaded chunks; the targeted Australia build indexed 49,089 pages into 124.9 MiB in 53.0 seconds, replacing a 222.0 MiB legacy index.
- Australia SHA `0dfa6b2` passed the final strict diagnostic render in 243.74 seconds with only 20 known informational stale-anchor messages.
- Production and smoke builds minify HTML while leaving inline JavaScript and CSS untouched; Australia output shrank by 46.4% in validation.
- Every family receives a Material landing page, and artifact validation rejects missing family roots or unrewritten current-family raw Markdown links.
- Recognized upstream `nav-card` tables render as accessible adaptive card grids with clean directory links and descriptions recovered from omitted-icon alt text.
- UI remediation covers table Markdown, fences, card variants, title and navigation normalization, responsive containment, and detector precision.
- The UI audit groups evidence under 10 semantic rules with documented triage and rebuild workflows; report paths cannot overlap the read-only input site.
- The retained Australia audit scanned 49,089 pages, rendered 143 at both viewports, recorded 9 findings without errors, and remains diagnostic.

## Known gaps and risks

- GitHub Actions publication to the rolling Release has not yet been proven in production.
- Full families remain large; Australia has roughly 49,000 pages and generates 4.03 GiB.
- Navigation usability still needs browser evaluation against a successful complete site.
- Australia contains 20 stale-anchor diagnostics at MkDocs' informational level; anchor validation intentionally remains informational.
- Cross-family links can still become stale when equivalent topics move between directories in different release branches.
- Pagefind has passed a targeted Australia production-family build and browser check, but a complete all-current-family production build and package assembly remain deferred.

## Next likely work

1. Review the retained Australia diagnostic site and UI report; scope any follow-up findings independently rather than treating zero findings as an implicit gate.
2. Rebuild every current family through the normal production fingerprint flow and measure Pagefind artifact and query performance.
3. Verify rolling Release reuse and publication.

Use the README virtual-environment workflow and `upstream.families` for local restrictions. Repository state remains authoritative.
