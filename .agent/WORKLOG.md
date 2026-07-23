# Work Log

Reverse-chronological record of significant project work. This is a historical index, not the source of truth for implementation details; consult `.agent/CONTEXT.md`, ADRs, the current code, tests, and Git history as appropriate.

Older entries are archived in [.agent/worklog/2026-H2.md](worklog/2026-H2.md).

## 2026-07-22 — Normalize malformed upstream presentation

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `Normalize malformed upstream presentation` (intended subject)

### Outcome

Added deterministic source-layer recovery for the malformed upstream presentation patterns cataloged during Australia UI auditing, improved responsive containment and detector precision, and retained a final diagnostic build and report for manual review without imposing a zero-finding gate.

### Changes and decisions

- Added deterministic recovery for Markdown inside raw and nested HTML tables, malformed inline fenced-code boundaries, linked, split-link, missing-alt-marker, and mixed linked/informational navigation cards, while preserving unfamiliar structures.
- Normalized recognized Markdown escapes in navigation and page-title metadata; retained the first navigation occurrence of each resolved destination because Material renders repeated destinations with the canonical page title.
- Added responsive table, code, link, and deeply nested mobile-list containment; refined browser clipping and viewport checks to ignore intentional Material navigation, fixed controls, responsive scroll containers, and Markdown syntax inside explicit code examples.
- Added upstream-shaped transformation, navigation, rendering, and audit regression fixtures covering every discovered pattern; no public CLI, report schema, configuration, or artifact contract changed.
- Recorded the normalization boundaries, navigation canonicalization, responsive policy, and report-only audit posture in ADR-0018.

### Verification

- The full suite passed with 123 tests and one filesystem-specific skip; `git diff --check` passed.
- The final strict Australia smoke render from retained workspace inputs at upstream SHA `0dfa6b2` completed in 243.74 seconds with only the 20 known informational stale-anchor messages.
- The retained UI audit scanned 49,089 HTML pages, rendered 143 selected pages at desktop and mobile viewports, and produced 9 grouped findings, 286 screenshots, and no audit errors. Findings remain available for manual review and were not used as an acceptance gate.
- A complete current-family production build, package validation, and Release publication remain deferred.

## 2026-07-22 — Reconcile ADR and agent records

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Protect UI audits from overlapping output paths` (intended subject)

### Outcome

Reconciled the complete ADR catalog and layered agent records with repository history while restoring comfortable size headroom in the active context and worklog.

### Changes and decisions

- Matched completed ADR and worklog entries to their committed SHAs, subjects, and known committer.
- Reviewed the accepted and superseded decision chain, index coverage, local links, and remaining pending records without rewriting accepted rationale.
- Condensed redundant current-state prose and moved the oldest active entries into the existing 2026-H2 archive.

### Verification

- Validated every indexed ADR, local Markdown link, and recorded commit subject against Git history.
- Confirmed context and active-worklog size limits and ran Markdown whitespace checks.

## 2026-07-22 — Define and enforce UI finding remediation

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** `Protect UI audits from overlapping output paths` (intended subject)

### Outcome

Turned UI-audit findings into a contributor workflow that fixes the earliest responsible source layer and regenerates complete families without patching generated files or introducing an automatic repair phase.

### Changes and decisions

- Documented triage ownership, regression-fixture expectations, smoke and production diagnostic builds, all-family release validation, and the existing package-wide fingerprint behavior.
- Enforced read-only audits by rejecting report paths equal to, nested below, or above the input site before `--clean` can remove anything.
- Added contract coverage proving audits do not invoke builds and pipeline changes rebuild every selected current family.
- Recorded the durable contributor workflow and family-level rebuild policy in ADR-0017.

### Verification

- The full suite passed with 110 tests and one filesystem-specific skip after granting loopback access for Chromium.
- Documentation links resolved, `CONTEXT.md` remained within its size limits, and `git diff --check` passed.

## 2026-07-22 — Introduce a versioned site-quality ruleset

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `c8f90dc` — `Define versioned site quality rules`

### Outcome

Made packaged Markdown rules the authoritative human-readable definition of sndocs.com site quality and grouped static and browser audit evidence under stable semantic rule IDs.

### Changes and decisions

- Added 10 active rules, strict lifecycle and prose validation, deterministic digesting, and explicit registration for 14 detectors with confidence independent from rule severity.
- Added `sndocs quality validate/list/show`; migrated local audit reports to schema version 2 with rule-grouped observations and an embedded active catalog.
- Documented contribution workflow and recorded the architecture and version-1 report break in ADR-0016.

### Verification

- The full suite passed with 106 tests and one filesystem-specific skip; wheel coverage confirmed all ruleset resources were packaged; `git diff --check` passed.
- The retained Australia audit scanned 49,090 pages, rendered 31 representatives at two viewports, produced five semantic rule findings with 51 screenshots, and detected all three reported defect classes without audit errors.

## 2026-07-22 — Add a local hybrid UI audit

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `dc50551` — `Add local hybrid UI audit`

### Outcome

Added a report-only local audit that scans every generated HTML page and renders deduplicated high-risk representatives plus a deterministic Chromium sample at desktop and mobile viewports.

### Changes and decisions

- Added `sndocs audit-ui` with safe report replacement, stable JSON, a browsable HTML summary, and screenshots for rendered findings.
- Detects leaked Markdown and escapes, duplicated navigation, unresolved local and Markdown links, overflow, browser errors, console errors, and failed resources without changing or gating generated sites.
- Kept Playwright optional, retained local-only operation, and recorded the command and report policy in ADR-0015.

### Verification

- The full suite passed with 88 tests and one filesystem-specific skip.
- The retained 2.3 GiB Australia production site audit scanned 49,090 pages, rendered 31 representatives at both viewports, and produced 134 grouped findings with 51 screenshots, including all three reported defect classes.

## 2026-07-22 — Suppress expected omitted-navigation diagnostics

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `f1e3031` — `Suppress expected omitted-navigation diagnostics`

### Outcome

Stopped expected MkDocs omitted-navigation listings from exhausting terminal history while preserving complete page rendering and strict validation.

### Changes and decisions

- Configured generated family builds to ignore only `validation.nav.omitted_files`, retained all other validation levels, and recorded the policy in ADR-0014.
- Added fixture coverage proving the expected list is absent while a genuine broken-link warning remains visible and fatal.

### Verification

- Full suite passed with 85 tests and one filesystem-specific skip; `git diff --check` passed.

## 2026-07-22 — Decouple runtime resources from configuration location

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `9945ef0` — `Fix config-independent runtime paths`

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
- **Committed by:** Victor Bilgin
- **Commit:** `a9bc31e` — `Simplify and harden sndocs CLI`

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
- **Committed by:** Victor Bilgin
- **Commit:** `f28f6db` — `Repair and restyle upstream navigation cards`

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
- **Committed by:** Victor Bilgin
- **Commit:** `7efa4ed` — `Clean up project records`

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
