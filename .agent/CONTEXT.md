# Project Context

Current-state handoff; use `.agent/WORKLOG.md`, ADRs, and Git history for detail.

## Objective

Build an independent versioned MkDocs mirror of `ServiceNow/ServiceNowDocs`.

## Current architecture

- `pipeline.toml` defines identity, upstream source, family selection, and artifact naming.
- `discovery.py` parses upstream `llms.txt`, preserves its family/publication ordering, and resolves release-branch SHAs.
- `source.py` provides remote and reusable-local exact-commit sources without changing branches.
- `navigation.py` converts publication indexes into MkDocs navigation; `transform.py` deterministically recovers known malformed source structures, enriches pages, rewrites links, renders cards/notices, and creates placeholders.
- `links.py` repairs stale same-family links using exact paths, unique basenames, publication context, self-canonical metadata, and reviewed overrides; unresolved ambiguity is fatal.
- `builder.py` builds and fingerprints families, creates family-scoped Pagefind indexes, selects deterministic preview samples, reuses production output, retains archives, and assembles manifests.
- `artifacts.py` validates the assembled site and creates ZIP/TAR archives with SHA-256 checksums.
- `deployment.py` plans latest-only releases, validates inventories, assembles archived metadata without family downloads, creates sharded recovery archives, and guards R2 cleanup.
- `worker/` contains the tested Cloudflare Worker and preview/production Wrangler environments bound privately to `sndocs-production`.
- `quality.py` validates packaged rules; `ui_audit.py` applies them through structural and sampled Chromium checks.
- `.github/workflows/build-site.yml` manually builds current latest, verifies immutable R2 releases through preview, pauses for protected production promotion, publishes recovery assets, and applies guarded cleanup. Scheduling remains disabled during rollout.

The `sndocs` 0.2 CLI manages the pipeline; optional `audit-ui` and `quality` commands expose report-only audits and human-readable rules.

## Important invariants and decisions

- Upstream `llms.txt` is authoritative for current families and publication ordering.
- Scheduled publication builds only current latest; every family previously published as latest remains under `/<family>/` as an immutable archive. Never-published upstream families remain absent.
- The public `sndocs build` default still builds every selected current family; deployment automation alone uses the latest-with-archives policy.
- Publication indexes define navigation, but all family Markdown is rendered; expected omitted-navigation listings are suppressed without weakening strict validation.
- Same-family moved links are repaired only through deterministic paths, canonical metadata, or reviewed overrides.
- Navigation retains its first resolved destination; missing targets receive diagnostic placeholders.
- Cross-family moved-link resolution is intentionally not attempted.
- MkDocs strict mode remains enabled; ambiguity and pipeline-created broken links fail.
- Production builds include a static Pagefind full-text index in every selected current family; smoke manifests are distinct and omit search; sampled preview manifests include search and coverage metadata. Neither diagnostic profile can be packaged.
- `sndocs preview` builds a deterministic strict sample with search; it is a sanity check rather than complete-family validation.
- Generated UI uses the `sndocs` brand and links to `vbilgin/sndocs.com`; ServiceNowDocs remains the content source.
- Existing output requires explicit `--clean` replacement; dry runs never write or delete files.
- Automatic workspaces are cleaned; explicit `--work-dir` content is preserved.
- Source prose receives light enrichment rather than editorial restructuring; intentionally omitted upstream media is not restored.
- Generated Markdown and HTML stay out of the main branch.
- Public family URLs resolve through a versioned Worker release binding and private R2 objects. Preview alone uses a mutable candidate pointer; production never does.
- Active and rollback releases, all archived-family artifacts, and a 14-day grace window are cleanup invariants.
- Topics use host-agnostic directory URLs (`/topic/` backed by `topic/index.html`); preview them over HTTP.
- Mirrored content retains required legal notices, independent-site disclaimer, and upstream link.

## Artifact contract

The assembled site contains:

- one directory for each current or archived family;
- a `pagefind/` search bundle inside each current production or preview family;
- `index.html` redirecting to the newest family;
- `versions.json` for the release selector;
- `build-manifest.json` with source SHAs, archive state, build profile, pipeline fingerprint, and link counts;
- schema-version-2 `link-report.json` with typed document/navigation repairs, missing-document placeholders, and omitted-image occurrences; and
- `SERVICENOW-LICENSE.txt`.

Public packaging still produces `sndocs-site.tar.gz`, `sndocs-site.zip`, and SHA-256 files for both. Cloudflare publication additionally uses per-family inventories and archives, small canonical release manifests, root archives, and deterministic numbered parts above 1.9 GiB.

## Current status

- Current families use Pagefind's query-loaded chunks; the targeted Australia build indexed 49,089 pages into 124.9 MiB in 53.0 seconds, replacing a 222.0 MiB legacy index.
- The deterministic Australia preview sample selects 159 of 48,989 Markdown files across all 55 top-level source areas while retaining strict rendering and Pagefind.
- Production and smoke builds minify HTML while leaving inline JavaScript and CSS untouched; Australia output shrank by 46.4% in validation.
- Artifact validation rejects missing roots, invalid search output, or unrewritten current-family source links. UI audits remain report-only.
- Latest-only release planning, root assembly, sharded recovery, retention cleanup, Worker routing/cache/header behavior, and both Wrangler environment configurations are implemented and locally tested.
- The first live Australia candidate and private preview Worker exist in Cloudflare. Preview acceptance exposed Browser Integrity Check rejecting Python's default user agent and full R2 reads being mislabeled as partial responses; local fixes preserve BIC and correct `200`/`206` semantics, pending bootstrap and a fresh publication.

## Known gaps and risks

- Production publication, apex certificates, rollback, GitHub recovery reconstruction, and cost behavior remain unproven in the live accounts.
- Full families remain large; Australia has roughly 49,000 pages and generates 4.03 GiB.
- Australia contains 20 stale-anchor diagnostics at MkDocs' informational level; anchor validation intentionally remains informational.
- Cross-family links can still become stale when equivalent topics move between directories in different release branches.
- Pagefind has passed a targeted Australia production-family build and browser check, but a complete all-current-family production build and package assembly remain deferred.

## Next likely work

1. Review the retained Australia diagnostic site and UI report; scope any follow-up findings independently rather than treating zero findings as an implicit gate.
2. Execute the deployment runbook: create the first candidate, bootstrap preview, promote, test rollback, re-promote, and observe for 48 hours.
3. Prove GitHub recovery reconstruction, complete two successful releases, then enable the daily schedule, guarded cleanup, and HSTS.

Use the README virtual-environment workflow and `upstream.families` for local restrictions. Repository state remains authoritative.
