# Work Log

Reverse-chronological record of significant project work. This is a historical index, not the source of truth for implementation details; consult `.agent/CONTEXT.md`, ADRs, the current code, tests, and Git history as appropriate.

Older entries are archived in [.agent/worklog/2026-H2.md](worklog/2026-H2.md).

## 2026-07-22 — Suppress expected omitted-navigation diagnostics

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Pending`

### Outcome

Stopped expected MkDocs omitted-navigation listings from exhausting terminal history while preserving complete page rendering and strict validation.

### Changes and decisions

- Configured generated family builds to ignore only `validation.nav.omitted_files`, retained all other validation levels, and recorded the policy in ADR-0014.
- Added fixture coverage proving the expected list is absent while a genuine broken-link warning remains visible and fatal.

### Verification

- Full suite passed with 85 tests and one filesystem-specific skip; `git diff --check` passed.

## 2026-07-22 — Decouple runtime resources from configuration location

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Fix config-independent runtime paths` (intended subject)

### Outcome

Allowed custom-named pipeline configuration files to live outside the repository root without redirecting packaged theme lookup, pipeline fingerprinting, or automatic workspace placement into the config directory.

### Changes and decisions

- Recorded the selected config path explicitly, resolved MkDocs overrides from the installed `sndocs` package, and based incremental fingerprints on effective settings plus installed package contents while excluding caches and bytecode.
- Anchored automatic `.temp/` workspaces to the CLI invocation directory and preserved explicit diagnostic workspaces.
- Kept the CLI and TOML schemas unchanged; manifests created with the former fingerprint may rebuild once when reused.

### Verification

- The full suite passed with 85 tests and one filesystem-specific skip; focused tests passed with 31 tests.
- A built wheel contained all 12 theme files, including templates, branding, stylesheets, and JavaScript.

## 2026-07-22 — Simplify and harden the sndocs CLI

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Pending`

### Outcome

Released the breaking 0.2 CLI contract with explicit reusable-source management, safe output replacement, clearer incremental reuse, per-run family selection, side-effect-free build planning, and deterministic human or JSON results.

### Changes and decisions

- Added `source clone/update/check`, consolidated local selection under `--source`, renamed reuse input to `--reuse-from`, and removed the superseded flags without aliases.
- Required `--clean` before replacing build output, added `--dry-run` and repeatable `--family`, retained one-family smoke semantics, and shared one planner between previews and execution.
- Routed progress to standard error, added concise summaries and single-object JSON output, detected `GITHUB_OUTPUT` automatically, documented ephemeral preview ports, and recorded the contract in ADR-0013.

### Verification

- Full suite passed with 85 tests and one filesystem-specific skip; focused strict production and smoke fixtures passed.
- CLI help inspection, Python compilation, and `git diff --check` passed.

## 2026-07-19 — Repair and restyle upstream navigation cards

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Pending`

### Outcome

Converted recognized upstream `nav-card` tables into responsive sndocs.com card grids, repairing Markdown links that previously appeared as partial text around omitted icons.

### Changes and decisions

- Deterministically extracted each card's title, destination, and omitted-icon alt text while preserving unfamiliar tables unchanged and collapsing empty cells.
- Generated fully clickable semantic cards with clean directory URLs, retained upstream table IDs, and preserved existing link-resolution reporting.
- Added adaptive branded card styling using the local Parchment, Carbon Black, Majorelle Blue, and Classic Crimson palette.

### Verification

- Full suite passed with 66 tests and one filesystem-specific skip; strict production and smoke MkDocs fixtures verified valid rendered anchors and absence of partial card Markdown.
- The upstream Australia ServiceNow Vault source produced six cards and no icon notices; browser checks at 1440×900 and 390×844 confirmed the branded surface, responsive single-column mobile layout, and no horizontal overflow.
- `git diff --check` passed.

## 2026-07-18 — Clean up project records

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Clean up project records` (intended subject)

### Outcome

Reconciled project context, worklog commit metadata, and ADR references with current Git history while keeping the active context files within their size limits.

### Verification

- Reviewed every file under `.agent/` and `docs/adr/`, verified indexed ADR links and referenced commit SHAs, and ran Markdown whitespace checks.

## 2026-07-18 — Strengthen ServiceNow attribution

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `27c6191` — `Strengthen ServiceNow attribution`

### Outcome

Added ServiceNow's required trademark and build-year copyright notices to the README and generated site footer while preserving the independent-mirror disclaimer and Apache-2.0 attribution.

### Changes and decisions

- Derived the generated footer copyright year from the UTC family build time and retained archived-family immutability.
- Added a footer link to the public `ServiceNow/ServiceNowDocs` repository and adjusted the footer presentation for the longer legal notices.
- Added strict rendered-site coverage for the notices, year, license wording, disclaimer, and repository link.

### Verification

- Full test suite passed with 59 tests and one filesystem-specific skip; `git diff --check` passed.
- The strict Material fixture rendered and verified the exact notices, UTC build year, preserved disclaimer, Apache-2.0 wording, and ServiceNowDocs repository link in both production and smoke configurations.

## 2026-07-18 — Minify generated family HTML

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `cf43b61` — `Minify generated family HTML`

### Outcome

Added deterministic HTML-aware minification to every production and smoke family build, materially reducing the generated site and packaged artifacts without changing the host-agnostic directory-URL contract.

### Changes and decisions

- Added and locked `mkdocs-minify-html-plugin` 0.3.11, declared its Python 3.11 `typing-extensions` compatibility requirement, enabled it after the optional search plugin, and explicitly disabled inline CSS and JavaScript minification.
- Added fixture coverage for plugin configuration, minified output, whitespace-sensitive code and textarea content, inline JavaScript preservation, and the existing clean-URL, branding, search, placeholder, and navigation behavior.
- Kept the minifier dependency in `pyproject.toml`, so the existing pipeline fingerprint invalidates prior unminified family reuse automatically.

### Verification

- Full test suite passed with 59 tests and one filesystem-specific skip; `git diff --check` passed.
- A strict Australia production rebuild at upstream SHA `71f4936` completed successfully: rendering took 253 seconds, all normalization counts matched the prior build, and artifact validation passed.
- Minification reduced Australia HTML from 4,077,612,994 to 2,065,897,587 bytes (49.3%) and the complete site from 4,333,444,164 to 2,321,729,890 bytes (46.4%); the representative page fell from 55,292 to 31,607 bytes.
- Packaging completed in 58.8 seconds; TAR.GZ fell from 433,174,392 to 350,614,880 bytes (19.1%) and ZIP fell from 476,180,101 to 401,874,869 bytes (15.6%).
- Browser validation confirmed the representative clean URL, title, heading, branding, release selector, search, canonical URL, adjacent-topic navigation, and all requested assets without console warnings or errors.

### Follow-up

- Retain the original and minified Australia outputs only as local ignored validation artifacts; defer a complete multi-family build until broader integration validation is needed.

## 2026-07-18 — Apply sndocs.com branding to Material

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `829859b` — `Apply sndocs.com branding to Material`

### Outcome

Applied the local sndocs.com visual identity to newly rendered family sites with a tracked logomark and favicon bundle, a Parchment light canvas, and contrast-safe brand colors.

### Changes and decisions

- Copied the supplied OnLight logomark and favicon assets into the tracked Material override tree while retaining `local/branding/` as the ignored editable source.
- Made favicon and web-manifest references family-relative and host-agnostic, including relative icon paths within the manifest.
- Assigned Carbon Black to text and the footer, Majorelle Blue to interactive states, Classic Crimson to structural accents, and Pumpkin Spice to warning surfaces.
- Preserved immutable archived-family output; current families receive the branding when the changed pipeline fingerprint triggers their next build.

### Verification

- Full test suite passed with 59 tests and one filesystem-specific skip; the strict Material fixture passed with production search enabled and smoke search disabled.
- Confirmed every copied logo and favicon image matches its ignored source byte-for-byte, all family-relative branding requests return successfully, and `git diff --check` passes.
- Browser inspection at 1440×900 and 390×844 verified the logo proportions, Parchment/Carbon surfaces, Blue interactive states, Crimson metadata and header accents, release selector, responsive layout, footer contrast, and absence of browser console warnings or errors.

### Follow-up

- Add a dark theme only after a complete dark-background asset treatment is available.

## 2026-07-18 — Preserve clean URLs and add local preview

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `683e6fd` — `Add clean URL preview server`

### Outcome

Made the clean directory-URL contract explicit and added a supported local HTTP preview workflow so generated navigation resolves topic index pages without exposing `index.html` in URLs.

### Changes and decisions

- Explicitly enabled MkDocs directory URLs and retained `/topic/` as the host-agnostic public URL form.
- Added `sndocs serve` with site, bind-address, and port options, missing-directory diagnostics, and graceful interruption handling using only the Python standard library.
- Documented why `file://` browsing cannot resolve directory indexes and recorded the CLI and URL policy in ADR-0012.

### Verification

- Full test suite passed with 59 tests and one filesystem-specific skip; Python compilation and `git diff --check` also passed.
- The retained Australia build served successfully through `sndocs serve`; `/australia/better-together/using-ham-for-esg/` returned HTTP 200 and interruption closed the server cleanly.

### Follow-up

- Use the preview command for browser evaluation of the retained Australia production build.

## 2026-07-17 — Normalize upstream strict-validation defects

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `20bc107` — `Normalize upstream validation defects`

### Outcome

Made the Australia source snapshot pass strict MkDocs rendering and artifact validation without suppressing warnings or fabricating missing content or media.

### Changes and decisions

- Shared the deterministic family resolver between document links and publication navigation, retained fatal ambiguity, and finalized placeholders after both reference passes.
- Converted 6 conventional references to 3 absent PNG targets into accessible omitted-image notices while leaving Markdown-looking text inside raw HTML containers unchanged.
- Published typed document, navigation, placeholder, and omitted-image audit data in `link-report.json` schema version 2 and converted retained schema-version-1 archived reports during assembly.
- Added a generated Material landing page for each family, tightened raw-link rewriting when an upstream URL is both link label and destination, and strengthened artifact schema and raw-link validation.
- Recorded the policy in ADR-0011 and kept stale-anchor validation at MkDocs' informational default.

### Verification

- Full test suite, Python compilation, and `git diff --check` passed.
- A render-free Australia audit at `71f4936517ebd1fbaf76c5515c40b8d12bc6dd5c` reported zero warnings and zero unrewritten current-family raw links; 20 stale anchors remained informational.
- A strict Australia production build with search completed and passed artifact validation in 310.5 seconds. It produced 220,021 exact, 15,207 repaired, and 271 missing document-link occurrences; 58,280 exact, 488 repaired, and 67 missing navigation occurrences; 98 placeholders; and 6 omitted images across 3 targets.
- The validated Australia family tree measured 4,327,910,259 bytes (4.03 GiB), including 238,443,879 bytes (227.4 MiB) of search data; the temporary tree was removed after measurement.
- Victor independently validated the retained Australia production build and packaged artifacts locally; `site-australia/` and `artifacts-australia/` are ignored for continued local inspection.

### Follow-up

- Evaluate the successful Australia site in a browser before attempting and packaging the complete four-family build.

## 2026-07-17 — Bound build storage and add a smoke profile

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `3198cfa` — `Optimize build storage and add smoke mode`

### Outcome

Reworked family build staging so temporary storage no longer accumulates source, transformed Markdown, and duplicate generated sites across all release families; added an explicit strict smoke profile for quick local testing.

### Changes and decisions

- Moved automatic workspaces under ignored `.temp/`, cleaned each completed family workspace, preserved explicit diagnostic work directories, and printed phase timing, size, reuse, and cleanup progress.
- Enabled Material navigation pruning, rendered MkDocs directly into final family outputs, and reused unchanged family trees with hard links plus a portable copy fallback.
- Streamed local `git archive` extraction instead of buffering the complete archive in memory.
- Added `build --smoke` for newest-family strict builds without search, recorded the profile in manifests, isolated incremental reuse by profile, and rejected smoke packaging.
- Recorded the workspace lifecycle and smoke artifact contract in ADR-0010.

### Verification

- Full test suite: 52 passed, 1 filesystem-specific skip; strict fixture builds passed with production search enabled and smoke search disabled.
- CLI help inspection, Python compilation, and `git diff --check` passed.
- An Australia production attempt measured 7.6 seconds and 256.6 MiB for source materialization, 61.1 seconds and 259.2 MiB for transformation, a 698 MiB peak automatic workspace on disk, 4.1 GiB of generated output, and a 227 MiB search directory.
- The measured build correctly removed its automatic workspace but MkDocs strict mode rejected 494 pre-existing upstream warnings: 488 stale navigation references and 6 missing-image references. Stale anchors were separate informational diagnostics, so no complete artifact or four-family build was attempted; the invalid 4.1 GiB measurement output was removed afterward.

### Follow-up

- Resolve or deterministically represent the Australia strict warnings before treating the 4.1 GiB generated tree as a valid artifact or attempting the complete multi-family build.

## 2026-07-17 — Resolve stale links using canonical metadata

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `33abe28` — `Resolve stale links using canonical metadata`

### Outcome

Added automatic, metadata-based resolution for ambiguous stale links whose candidates contain one uniquely self-canonical page, while retaining reviewed overrides for genuine metadata ties.

### Changes and decisions

- Centralized frontmatter parsing and indexed exact ServiceNow canonical-path identities in the family link resolver.
- Applied self-canonical resolution after path-based rules and before explicit overrides, making the behavior independent of family, referring page, or predefined target.
- Removed the pending Source-to-Pay glossary override, retained the tied formatter override, and recorded the policy in ADR-0009.
- Added regression coverage for unseen referring pages, another upstream duplicate pattern, malformed frontmatter, escaped paths, invalid metadata, tied canonical candidates, and override fallback.

### Verification

- Full test suite: 42 passed, 1 filesystem-specific skip.
- Australia-wide transformation completed with 219,983 exact links, 15,225 repaired links, 121 placeholders, and zero ambiguities.
- `git diff --check` passed.

## 2026-07-17 — Add reusable local upstream sources

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `49f4ae1` — `Add reusable local upstream source support`

### Outcome

Enabled offline discovery and faster repeated builds from a reusable full clone of `ServiceNow/ServiceNowDocs` while preserving exact commit SHA and incremental-reuse semantics.

### Changes and decisions

- Added `--source-repo` and `--clone-source` to discovery and build, with explicit `--refresh-source` fetching for existing clones.
- Required clean local clones and one matching GitHub remote, then read authoritative metadata and family SHAs from remote-tracking refs.
- Exported exact commits into isolated workspaces without switching or modifying the reusable clone.
- Moved source preparation ahead of output removal and recorded the reproducible local-snapshot policy in ADR-0008.

### Verification

- Full test suite: 32 passed, 1 filesystem-specific skip.
- CLI help inspection passed for discovery and build source options.
- Strict fixture build, Python compilation, and `git diff --check` passed.

## 2026-07-17 — Override an ambiguous Australia formatter link

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `142924d` — `Allow narrowly scoped overrides for ambiguous stale links`

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
- **Commit:** `0a78be3` — `docs: establish layered project context and agent guidance`

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
