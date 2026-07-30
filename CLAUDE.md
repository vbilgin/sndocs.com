# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

[AGENTS.md](AGENTS.md) is the authoritative operating contract for this repository and applies to Claude Code as written. It defines the context-loading sequence, repository rules, verification expectations, and the Git/handoff policy. Follow it; this file adds orientation, not exceptions.

The context system is layered (ADR-0006):

- [AGENTS.md](AGENTS.md) — short, stable repository instructions.
- [.agent/CONTEXT.md](.agent/CONTEXT.md) — bounded current-state handoff (< 150 lines / 1,000 words). Read it in full before substantial work; update it only when material work changes architecture, invariants, interfaces, status, risks, or next steps.
- [.agent/WORKLOG.md](.agent/WORKLOG.md) — reverse-chronological significant work; search it selectively, never load it wholesale. Older entries archive to `.agent/worklog/YYYY-HN.md`.
- [docs/adr/](docs/adr/README.md) — 24 accepted ADRs (plus superseded history) that are current policy. Read only the relevant ones. Never rewrite accepted rationale; supersede with a new numbered ADR added to `docs/adr/README.md`.

Repository state is authoritative over documentation. Report conflicts rather than silently picking one.

Prose convention in all repository Markdown: keep each paragraph and list item on a single source line.

## Commands

Environment (Python 3.11+; the checked-out `.venv` runs 3.14):

```bash
python -m venv .venv && .venv/bin/python -m pip install -r requirements.lock && .venv/bin/python -m pip install --no-deps -e '.[test]'
```

Python tests — required for any Python change:

```bash
.venv/bin/pytest
```

A single test, file, or pattern (`addopts = -q` is already configured):

```bash
.venv/bin/pytest tests/test_links.py::test_unique_moved_target_is_repaired
```

Cloudflare Worker tests and Wrangler config validation:

```bash
npm ci --prefix worker && npm test --prefix worker
```

```bash
XDG_CONFIG_HOME=/tmp/sndocs-wrangler WRANGLER_LOG_PATH=/tmp/sndocs-wrangler.log npm run check --prefix worker
```

There is no browser dependency: `sndocs audit-ui` is a static-only scan (ADR-0024), and every test runs without Playwright or Chromium.

Documentation-only changes: verify referenced paths and links, inspect Markdown structure, and run `git diff --check`.

### Pipeline CLI

Reusable offline upstream clone (avoids network on every run; must be clean with exactly one remote matching `upstream.repository`):

```bash
.venv/bin/sndocs source clone ../ServiceNowDocs && .venv/bin/sndocs source check ../ServiceNowDocs
```

```bash
.venv/bin/sndocs discover --source ../ServiceNowDocs
```

Fastest useful checks, in increasing cost — prefer these over full builds, which are network-, disk-, and time-intensive:

```bash
.venv/bin/sndocs preview --output site-preview --source ../ServiceNowDocs
```

```bash
.venv/bin/sndocs build --output site-smoke --source ../ServiceNowDocs --smoke --family australia
```

```bash
.venv/bin/sndocs build --output site-diagnostic --source ../ServiceNowDocs --family australia
```

Full pipeline: `build` → `validate` → `package`. `audit-ui` and `quality` are report-only diagnostics. `serve --site DIR` serves a completed site over HTTP (required — clean directory URLs do not work over `file://`). Publication has no CI — it is a manual, operator-run sequence documented in [docs/deployment-runbook.md](docs/deployment-runbook.md) (ADR-0023), built from two internal modules rather than public CLI surface: `python -m sndocs.deployment_cli` (`plan`, `inventory`, `assemble`, `validate`, `verify-*`, `package`, `reconstruct`, `cleanup-plan`, `cleanup-batches`) holds pure, file-in/file-out release logic with no network or subprocess calls; `python -m sndocs.publish_cli` (`resolve-active`, `push-family`, `assemble-candidate`, `push-candidate`, `promote`, `recovery-manifest`, `cleanup`) is the only place R2 uploads, `wrangler`, and `gh` are actually invoked.

CLI safety contract (ADR-0013): existing output is never replaced implicitly — `--clean` is required; `--dry-run` never writes or deletes; `--reuse-from` must differ from `--output`; finite commands print one JSON object on stdout with `--json` while progress goes to stderr.

## Architecture

A build is a deterministic transformation of an upstream Git snapshot into a host-agnostic versioned MkDocs Material site, then into immutable published objects. `src/sndocs/` holds the stages, roughly in pipeline order:

- `config.py` / `pipeline.toml` — site identity, upstream repository and `llms.txt` path, optional family allowlist, archive basename.
- `discovery.py` — parses upstream `llms.txt`; it is the authority for which families exist, their ordering, and publication ordering. Resolves exact release-branch SHAs.
- `source.py` — `RemoteSource` (GitHub) and `LocalSource` (clean local clone, read through remote-tracking refs without branch switching).
- `navigation.py` — turns each publication's `index.md` into MkDocs navigation.
- `transform.py` — deterministic per-document work: recovering known malformed upstream structures, enriching prose lightly, rewriting raw GitHub links to site links, rendering cards/notices, writing placeholders for missing targets.
- `links.py` — repairs stale same-family links via exact paths, unique basenames, publication context, self-canonical metadata, then reviewed overrides. Unresolved ambiguity raises `AmbiguousLinkError` and fails the build. Cross-family repair is intentionally not attempted.
- `builder.py` — the orchestrator: build planning (`plan_build`, shared by `--dry-run` and real builds), per-family builds, Pagefind indexing, deterministic preview sampling, reuse of unchanged families, archive retention, manifest assembly, and the package-wide `pipeline_fingerprint`.
- `artifacts.py` — strict validation of an assembled site plus ZIP/TAR packaging with SHA-256 sums.
- `quality.py` + `quality_rules/` — the versioned ruleset: Markdown rules with strict YAML frontmatter, stable permanent `SND-*` IDs, and registered detectors.
- `ui_audit.py` — applies the ruleset's static detectors to every generated page. Report-only: findings never fail the command. Five rules (overflow, clipping, page/console errors, failed resources) have `assessment: manual` and no detector — see ADR-0024.
- `deployment.py` / `deployment_cli.py` — pure, side-effect-free release logic: latest-only planning, inventories (with recovery metadata), candidate assembly, deterministic archives and >1.9 GiB sharding, upload verification, and cleanup planning. No network or subprocess calls.
- `r2.py` — a thin `aws` CLI subprocess wrapper (list/get/put objects and trees, batch delete) with an injectable runner for testing. All R2 I/O lives here and nowhere else.
- `publish_cli.py` — the only module with irreversible side effects: orchestrates `deployment.py` + `r2.py` + `wrangler` + `scripts/verify_deployment.py` into the publication sequence documented in the runbook.
- `theme/` — overrides, branding assets, and the version-selector JavaScript. `main.html` tags the content article with `data-pagefind-body` so Pagefind's scan boundary is a portable attribute rather than a Material CSS class.

Around that: `worker/` is the Cloudflare Worker serving private R2 objects through a version-pinned release binding; `scripts/verify_deployment.py` performs stdlib-only HTTP deployment verification (release header, range requests, 404s) used by `publish_cli promote`.

### Build profiles

Three mutually exclusive profiles recorded in `build-manifest.json` as `build_profile`, none convertible into another and only `production` packageable:

- `production` (default) — every selected current family, all Markdown rendered, chunked Pagefind index per family, minified HTML.
- `smoke` — one family (newest unless `--family` names one), no search; fast strict check.
- `preview` — every selected family, strict, with search and the version selector, but only a deterministic sample of documents (each top-level source area's `index.md`, its first valid topic, and one path-hash selection) plus a generated coverage page.

### Invariants worth knowing before you change behavior

- MkDocs strict mode stays on. Ambiguity and pipeline-created broken links are fatal. Expected omitted-navigation listings are suppressed without weakening strict validation (ADR-0014); stale-anchor diagnostics remain informational by choice.
- Publication indexes define navigation, but all family Markdown is rendered.
- Publication builds only current latest; every family previously published as latest stays under `/<family>/` as an immutable archive. `sndocs build` still defaults to all selected current families — the latest-with-archives policy belongs to `publish_cli` only.
- Upstream meaning is preserved. Recovery of malformed source data must be deterministic and auditable; intentionally omitted upstream media is not restored; enrichment is not editorial restructuring.
- Topics use host-agnostic directory URLs (`/topic/` backed by `topic/index.html`).
- Generated Markdown, HTML, build directories, downloaded upstream repos, packaged artifacts, caches, and virtual environments are never committed.
- Automatic workspaces below `.temp/` are cleaned; an explicit `--work-dir` is preserved (and can be large).
- Mirrored content retains its legal notices, upstream link, Apache-2.0 attribution, and the independent-site disclaimer.

### Fixing a rendering or UI defect

Follow [docs/ui-remediation.md](docs/ui-remediation.md) (ADR-0017): fix the earliest responsible layer — transformation, links, navigation, theme, MkDocs config, or the detector itself — never generated Markdown or HTML, and never with a generic post-build repair pass. Reduce the finding to the smallest upstream-shaped fixture, then rebuild at family granularity: one complete family is the smallest safe rendering unit.

### Deployment

[docs/deployment-runbook.md](docs/deployment-runbook.md) (ADR-0022, ADR-0023) governs publication. There is no CI: the operator runs the runbook's commands from their own machine, and `publish_cli promote --i-reviewed-preview` refuses to proceed unless that flag is passed after the manual preview checklist — the flag is the only record that the checklist happened. `pointers/production.json` is the fail-closed answer to "what is live"; the Worker never reads it. Do not treat deployment steps as routine verification, and do not make an R2 origin public to work around the Worker.

## Dependencies and branding

Prefer existing dependencies. A new one needs justification, a `pyproject.toml` change, and a regenerated `requirements.lock`.

`local/` is Git-ignored and absent from clones and CI. It holds the authoritative branding reference (`local/branding/brand_colors.json`, exported logomark SVGs, `design_files/logo.ai`) — consult it before touching branded site, README, or repository materials, and preserve supplied assets rather than approximating them. It also holds local test-build workspaces (`local/test_builds/`).
