# Project Context

Current-state handoff; see `.agent/WORKLOG.md`, ADRs, and Git history for detail.

## Objective

Build an independent versioned MkDocs mirror of `ServiceNow/ServiceNowDocs`.

## Current architecture

- `pipeline.toml` defines identity, upstream source, family selection, and archive naming.
- `discovery.py` parses `llms.txt`, preserves family/publication ordering, and resolves release-branch SHAs.
- `source.py` provides remote and reusable-local exact-commit sources without branch switching.
- `navigation.py` converts publication indexes into MkDocs navigation; `transform.py` deterministically recovers malformed source structures, enriches pages, rewrites links, renders cards/notices, and creates placeholders.
- `links.py` repairs stale same-family links using exact paths, unique basenames, publication context, self-canonical metadata, and reviewed overrides; unresolved ambiguity is fatal.
- `builder.py` builds and fingerprints families, creates Pagefind indexes, selects preview samples, reuses production output, retains archives, and assembles manifests. The fingerprint also hashes installed `mkdocs`/`mkdocs-material` versions.
- `artifacts.py` validates the assembled site and creates ZIP/TAR archives with SHA-256 checksums; `deployment.py`/`deployment_cli.py` are pure — release planning, inventory validation, archived-family assembly, sharded recovery, and cleanup planning that now refuses to run unless every protected release carries recovery metadata.
- `r2.py` wraps the `aws` CLI for all R2 I/O; `publish_cli.py`, the only module with irreversible side effects, orchestrates `r2.py`, `deployment.py`, `wrangler`, and `verify_deployment.py` per the runbook.
- `worker/` contains the tested Cloudflare Worker and preview/production Wrangler environments bound privately to `sndocs-production`.
- `quality.py` validates packaged rules; `ui_audit.py` now applies only static detectors. Five rules (overflow, clipping, page/console errors, failed resources) are `assessment: manual`, checked by hand against `sndocs serve`.
- Publication has no CI; the operator runs `publish_cli`, gated by `promote --i-reviewed-preview`; `pointers/production.json` in R2 records what is live, unread by the Worker.

The `sndocs` 0.2 CLI manages the pipeline; `audit-ui` and `quality` expose report-only audits and human-readable rules.

## Important invariants and decisions

- Upstream `llms.txt` is authoritative for current families and publication ordering.
- Publication builds only current latest; every family previously published as latest remains under `/<family>/` as an immutable archive. Never-published upstream families remain absent.
- `sndocs build` still defaults to every selected current family; `publish_cli` alone uses the latest-with-archives policy.
- Publication indexes define navigation, but all family Markdown is rendered; expected omitted-navigation listings are suppressed without weakening strict validation.
- Same-family moved links are repaired only through deterministic paths, canonical metadata, or reviewed overrides; cross-family resolution is not attempted. Navigation retains its first resolved destination; missing targets receive diagnostic placeholders.
- MkDocs strict mode remains enabled; ambiguity and pipeline-created broken links fail.
- Production builds include a static Pagefind index scoped by a `data-pagefind-body` attribute on the content article; smoke omits search; preview includes search and coverage metadata. Neither diagnostic profile can be packaged.
- `sndocs preview` builds a deterministic strict sample with search; a sanity check, not complete-family validation.
- Generated UI uses the `sndocs` brand and links to `vbilgin/sndocs.com`; mirrored content retains required legal notices, independent-site disclaimer, and upstream link.
- Existing output requires explicit `--clean`; dry runs never write or delete files; automatic workspaces are cleaned but `--work-dir` content is preserved.
- Source prose receives light enrichment, not editorial restructuring; intentionally omitted upstream media is not restored; generated Markdown/HTML stay out of the main branch.
- Public family URLs resolve through a versioned Worker release binding and private R2 objects. Preview alone uses a mutable pointer; production never does, including the new `pointers/production.json` planning record.
- Active and rollback releases, all archived-family artifacts, and a 14-day grace window are cleanup invariants; a protected release without recovery metadata now blocks cleanup planning.
- Topics use host-agnostic directory URLs; preview them over HTTP.

## Artifact contract

The assembled site contains:

- one directory for each current or archived family;
- a `pagefind/` search bundle inside each current production or preview family;
- `index.html` redirecting to the newest family;
- `versions.json` for the release selector;
- `build-manifest.json` with source SHAs, archive state, build profile, pipeline fingerprint, and link counts;
- schema-version-2 `link-report.json` with typed document/navigation repairs, missing-document placeholders, and omitted-image occurrences; and
- `SERVICENOW-LICENSE.txt`.

Public packaging still produces `sndocs-site.tar.gz`, `sndocs-site.zip`, and SHA-256 files for both. Cloudflare publication additionally uses per-family inventories, small canonical release manifests, root archives, and deterministic numbered parts above 1.9 GiB. `sndocs audit-ui` reports are schema-version-3, static-only.

## Current status

- Australia Pagefind indexes 49,089 pages in 124.9 MiB, down from 222.0 MiB; `data-pagefind-body` reproduces this scoping without the Material selector (structurally verified, not re-measured).
- The deterministic Australia preview samples 159 of 48,989 Markdown files across all 55 top-level areas; minified production/smoke HTML is 46.4% smaller.
- Artifact validation rejects missing roots, invalid search output, or unrewritten source links. UI audits remain report-only.
- Release planning, root assembly, sharded recovery, retention cleanup, and Worker routing/cache/header behavior are implemented and locally tested.
- GitHub Actions and Playwright are both gone; `audit-ui` is static-only, with SND-LAYOUT-001/002 and SND-FUNC-001/002 assessed manually per the preview checklist. The local publish runbook (ADR-0023) first ran against the live bucket on 2026-08-01, promoting `sndocs.com`; two `publish_cli` gaps and two runbook doc gaps were fixed (`.agent/WORKLOG.md`).

## Known gaps and risks

- Steady-state rollback and recovery reconstruction remain unproven under `publish_cli`.
- Manual preview validation can miss regressions an automated pass would catch; this is the accepted permanent design, not a gap to close.
- Full families remain large — Australia has roughly 49,000 pages, 4.03 GiB — with 20 stale-anchor diagnostics at MkDocs' informational level, left informational by intent.
- Cross-family links can still go stale when topics move between directories in different release branches.
- `transform.py` is still regex-based; known defects include unclosed tables and `.md` hrefs that `link-report.json` misses. A parser-based rewrite is next.

## Next likely work

1. Exercise steady-state rollback and `deployment_cli reconstruct` recovery now that a real release exists, closing the gaps above.
2. Replace `transform.py`'s regex layer with a parser-based segmenter, add real upstream fixtures, and make well-formedness a validation gate.
3. Time-box a Zensical spike against the seven documented criteria once the transform rewrite lands; do not merge it into that work.

Use the README venv workflow and `upstream.families` for local restrictions. Repository state remains authoritative.
