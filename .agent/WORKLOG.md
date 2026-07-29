# Work Log

Reverse-chronological record of significant project work. This is a historical index, not the source of truth for implementation details; consult `.agent/CONTEXT.md`, ADRs, the current code, tests, and Git history as appropriate.

Older entries are archived in [.agent/worklog/2026-H2.md](worklog/2026-H2.md).

## 2026-07-29 — Repair deterministic family-inventory ordering

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** Pending (`Repair deterministic family-inventory ordering` intended subject)

### Outcome

Corrected the family inventory generator after the first complete Australia publication build exposed a mismatch between filesystem `Path` ordering and the inventory validator's serialized POSIX path ordering.

### Changes and decisions

- Sort completed inventory entries lexically by their serialized `path` field before deriving the tree digest, preserving the existing validator, schema, artifact IDs, and deterministic inventory contract.
- Added a regression fixture with prefix-colliding directories to exercise the ordering difference that small deployment fixtures previously missed.
- Kept the fix within the accepted Cloudflare release design; no architecture decision or public interface changed.

### Verification

- The focused prefix-collision regression and all 11 deployment tests passed.
- The full Python suite passed with 155 tests and one environment-specific skip after enabling loopback access for browser/UI tests; `git diff --check` passed.

## 2026-07-28 — Repair first publication CI gate

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** Pending (`Repair first publication CI gate` intended subject)

### Outcome

Corrected the clean-runner assumptions that stopped the first live publication attempt before discovery, and migrated both deployment workflows and Worker tooling to Node 24.

### Changes and decisions

- Made the Material theme fixture validate installed package resources, locked Hatchling and its classifier dependency for the no-isolation wheel test, and installed Chromium before the complete CI test suite.
- Upgraded the official checkout, Python, Node, upload-artifact, and download-artifact actions to their current Node 24-compatible majors while preserving artifact names, paths, and inputs.
- Kept the non-editable CI package installation so publication continues to exercise the installed distribution layout.

### Verification

- The four previously failing tests passed; the full suite passed with 154 tests and one environment-specific skip, including Chromium and a separately installed wheel.
- Eight Worker tests and both Wrangler dry runs passed under Node 24.18.0; workflow parsing, action-version checks, and `git diff --check` passed. A corrected live dispatch awaits commit and push authorization.

## 2026-07-28 — Implement latest-release Cloudflare deployment

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `3411dec` — `Implement latest-release Cloudflare deployment`

### Outcome

Implemented a private-R2 and versioned-Worker deployment system that publishes only current latest while retaining every previously published latest family as an immutable public archive.

### Changes and decisions

- Added canonical latest-only planning, family and release inventories, archived-root assembly, exact remote inventory checks, deterministic sharded recovery, and guarded 14-day cleanup without changing the public build CLI.
- Added one tested Worker with private preview and production R2 bindings, clean URL and family-404 routing, ranges and conditionals, correct MIME data, release-separated caching, preview no-indexing, and report-only CSP.
- Replaced the monolithic workflow with test/plan, bounded latest build, candidate assembly, browser preview, protected production promotion with rollback, rolling recovery publication, and cleanup jobs; added a protected manual bootstrap workflow and intentionally left scheduling disabled.
- Added the operational runbook and ADR-0022, superseding the all-current scheduled publication and monolithic rolling-artifact deployment policies while retaining local full builds and the existing monolith during recovery proof.

### Verification

- The full Python suite passed with 154 tests and one environment-specific skip; Worker request tests and Wrangler dry runs passed for both environments.
- Python compilation, workflow YAML parsing, documentation/link structure checks, and whitespace checks passed. A real multi-gigabyte family build and live Cloudflare rollout remain post-implementation operations.

## 2026-07-28 — Add fast sampled preview command

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** Pending (`Add fast sampled preview command` intended subject)

### Outcome

Added a deterministic production-like preview that samples every selected family's source areas, builds strict searchable output, validates it, and serves it on an available local port.

### Changes and decisions

- Added `sndocs preview` with safe output replacement, selected-family support, automatic Pagefind generation, validation before serving, random-port allocation, and clean interruption without automatic browser launch.
- Selected every source-area index plus up to two deterministic topics per area; the Australia source yields 159 of 48,989 Markdown files across 55 areas.
- Kept sampled navigation local, externalized links to omitted existing topics as human-readable GitHub source links, retained genuine missing-target placeholders, and recorded preview coverage in manifests.
- Added preview-only validation and packaging boundaries without changing production, smoke, reuse, archive, or schema-version contracts.
- Documented the workflow and recorded its intentionally limited validation role in ADR-0021.

### Verification

- Targeted sampler, transformation, strict MkDocs, Pagefind, artifact, CLI, and existing profile tests passed; the full suite passed with 144 tests and one environment-specific skip.
- A real Australia preview at SHA `ea4a4a3` selected 159 of 48,989 Markdown files, transformed them in 2.4 seconds, rendered strict MkDocs output in 9.0 seconds, indexed 227 generated pages in 0.9 seconds, passed artifact validation, served on an allocated localhost port, and stopped cleanly.
- Context and worklog limits, Python compilation, documentation structure, and `git diff --check` passed.

## 2026-07-28 — Update site header and branding

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Commit:** Pending (`Update site header and branding` intended subject)

### Outcome

Updated generated family sites to use the `sndocs` UI brand, automatically hide the Material header while scrolling, and link to the `vbilgin/sndocs.com` project repository from desktop and mobile navigation.

### Changes and decisions

- Added independent site-repository URL and name settings without changing the `ServiceNow/ServiceNowDocs` upstream source contract.
- Enabled Material's `header.autohide` feature and emitted the configured repository metadata with the bundled GitHub icon for every production and smoke family build.
- Renamed the generated family title base, footer disclaimer, root redirect title, and web-app manifest while retaining the `sndocs.com` public domain and repository-facing project labels.
- Added configuration and strict rendered-fixture coverage for the new identity, repository link placements, and both search profiles.
- Recorded the UI-brand boundary, independent site-repository identity, and standard Material header behavior in ADR-0020.
- Compacted current context, archived the two oldest active worklog entries, restored archive ordering, and reconciled committed metadata for ADRs 0017–0019.

### Verification

- Targeted configuration, Material fixture, and build-reporting tests passed with 11 tests.
- The full suite passed with 136 tests and one environment-specific skip; `git diff --check` passed.
- ADR index coverage, local Markdown links, context/worklog size limits, and recorded commit SHAs were verified.

## 2026-07-28 — Replace monolithic Material search with Pagefind

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `b41ea68` — `Replace monolithic search with Pagefind`

### Outcome

Replaced the unusable 222 MiB Australia Material/Lunr search index with family-scoped Pagefind bundles that retain full-text search while loading compressed query-relevant chunks.

### Changes and decisions

- Added the pinned standard Pagefind binary, a fail-fast post-render indexing phase limited to article content, dependency-aware fingerprints, and current-production artifact validation while preserving smoke and archived-family behavior.
- Replaced Material's search UI with Pagefind's accessible modal, family-relative runtime URL resolution, and the established sndocs.com palette.
- Added fixture, failure, validation, and live Chromium coverage for body-text queries, nested pages, click and keyboard opening, no-result and Escape behavior, clean result navigation, resource loading, and console errors.
- Recorded the static search architecture in ADR-0019, superseding only the search portion of ADR-0003.

### Verification

- The full suite passed with 135 tests and one environment-specific skip; `git diff --check` passed.
- The strict targeted Australia production build indexed 49,089 pages and 426,812 words into 876 query-loaded chunks in 53.0 seconds. The 124.9 MiB logical Pagefind bundle replaced the 222.0 MiB monolithic Material index, and artifact validation passed.
- Live browser checks returned the expected clean family URL for title, body-only, and uncommon-term queries within the 10-second timeout, excluded quoted footer text, loaded Pagefind assets successfully, and produced no browser warnings.
- A complete all-current-family production build and package assembly remain deferred.

## 2026-07-22 — Normalize malformed upstream presentation

- **Work performed by:** Codex, with direction from Victor Bilgin
- **Committed by:** Victor Bilgin
- **Commit:** `4ac9816` — `Normalize malformed upstream presentation`

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
- **Committed by:** Victor Bilgin
- **Commit:** `c8c71fc` — `Protect UI audits from overlapping output paths`

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
- **Committed by:** Victor Bilgin
- **Commit:** `c8c71fc` — `Protect UI audits from overlapping output paths`

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
