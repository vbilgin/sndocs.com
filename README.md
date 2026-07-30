# sndocs.com

`sndocs.com` builds a host-agnostic, versioned MkDocs Material site from the public
[`ServiceNow/ServiceNowDocs`](https://github.com/ServiceNow/ServiceNowDocs) repository.
It is an independent community mirror and is not affiliated with or endorsed by ServiceNow.

The pipeline reads upstream `llms.txt`, discovers release-family branches and publications,
uses each publication's `index.md` as its navigation authority, rewrites raw GitHub Markdown
links into site links, and emits one site below `/<family>/`. A root redirect selects the newest
family. When upstream removes an old family, its last successfully built HTML remains in the
next artifact and is marked archived.

## Development

Python 3.11 or newer is required.

```shell
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e '.[test]'
.venv/bin/pytest
```

Discover the current upstream structure without building it:

```shell
.venv/bin/sndocs discover
```

For faster repeated testing, create and verify a reusable full upstream clone, then use it offline:

```shell
.venv/bin/sndocs source clone ../ServiceNowDocs
.venv/bin/sndocs source check ../ServiceNowDocs
.venv/bin/sndocs discover --source ../ServiceNowDocs
.venv/bin/sndocs build --output site --source ../ServiceNowDocs
```

The local clone must be clean and have exactly one SSH or HTTPS remote matching `upstream.repository`. Normal local runs use its committed remote-tracking refs without network access or branch switching. Refresh and verify those refs explicitly when desired:

```shell
.venv/bin/sndocs source update ../ServiceNowDocs
```

`source clone` fails if its destination already exists. Local paths are intentionally per-run CLI inputs rather than project configuration.

Build a complete site, optionally reusing a previously unpacked artifact:

```shell
.venv/bin/sndocs build --output site --reuse-from previous-site
.venv/bin/sndocs validate --site site
.venv/bin/sndocs package --site site --destination artifacts
```

An existing output is never removed implicitly. Pass `--clean` to replace one after source discovery and validation succeed. `--reuse-from` must identify a separate assembled site.

Automatic build workspaces are created below the ignored `.temp/` directory in the directory where `sndocs` is invoked, independent of the selected configuration file's location, and removed as each family finishes. Supply a fresh `--work-dir` path to preserve source snapshots, transformed Markdown, and MkDocs configuration for diagnostics; preserved workspaces can be large and are not cleaned automatically.

Use smoke mode for a fast, strict local check of the newest family without search indexing:

```shell
.venv/bin/sndocs build --output site-smoke --source ../ServiceNowDocs --smoke
.venv/bin/sndocs validate --site site-smoke
```

Smoke manifests are marked with `build_profile: smoke` and cannot be packaged as production
artifacts. Production remains the default: it renders all Markdown and creates an independent,
chunked Pagefind full-text index inside every current release family. Search stays fully static and
loads query-relevant chunks from the family artifact; it needs no hosted service or special web
server configuration. Material navigation prunes inactive branches from each page so the full
navigation hierarchy does not multiply the generated HTML size. Repeat `--family NAME` to override
`upstream.families` for one run while preserving upstream ordering. Smoke accepts at most one
selected family; without one it uses the newest family.

For the fastest production-like visual check, build and serve a deterministic sample:

```shell
.venv/bin/sndocs --config ./local/test_builds/aus/pipeline.australia.toml preview --output ./local/test_builds/aus/site --source ../australia
```

Preview includes every selected family, strict MkDocs rendering, the version selector, and Pagefind
search. Within each family it transforms every top-level source-area `index.md`, the first valid
topic declared by that index, and one additional stable path-hash selection. The current Australia
source selects 159 of 48,989 Markdown files across 55 source areas. A generated coverage page lists
the complete sample, while links to existing topics outside the sample open the corresponding
GitHub source. Preview output is marked with `build_profile: preview`, cannot be reused as another
profile, and cannot be packaged as a production artifact.

The command validates the completed sample and then serves it on `127.0.0.1` using an available
port, printing the exact URL before it waits. Use `--bind` or `--port` to override the server
address, and press Ctrl-C to stop it; the generated output remains available afterward. Existing
output still requires `--clean`. Preview deliberately has no `--json`, `--dry-run`, `--smoke`, or
`--reuse-from` mode and does not open a browser. It is a quick transformation, navigation, theme,
assembly, and search check—not a substitute for complete-family smoke or production validation.

Preview incremental decisions without writing or deleting files:

```shell
.venv/bin/sndocs build --dry-run --reuse-from previous-site --source ../ServiceNowDocs
```

Finite commands accept `--json` before or after the command and emit one JSON object on standard
output while progress goes to standard error.

Preview any completed build through the local web server:

```shell
.venv/bin/sndocs serve --site site-australia
```

Then open `http://127.0.0.1:8000/`. The generated site uses clean directory URLs such as
`/australia/better-together/using-ham-for-esg/`; the corresponding file on disk is
`using-ham-for-esg/index.html`. Opening the output through `file://` is not supported because the
filesystem protocol does not serve a directory's `index.html` automatically. Use `--bind` or
`--port` to override the preview server defaults; `--port 0` selects an available port.

### Local UI audit

Audit every generated HTML file structurally with the static site-quality detectors:

```shell
.venv/bin/sndocs audit-ui --site site --output ui-report
```

The command writes a browsable `index.html` and a stable `findings.json`. It is intentionally
report-only: findings do not produce a failing exit status. Existing report directories are
preserved unless `--clean` is supplied. This is a static scan with no browser dependency; per
[ADR-0024](docs/adr/0024-validate-generated-ui-without-a-browser.md), page overflow, clipped
components, uncaught page errors, console errors, and failed resource loads are assessed manually
with `sndocs serve` as part of the [deployment runbook's](docs/deployment-runbook.md) preview
checklist instead of by an automated browser pass. Generated reports are local artifacts and
should not be committed.

The schema-version-3 report groups observations from the static detectors under stable
semantic rule IDs. Rule severity describes impact, while detector confidence describes how
certain each observation is. Every report records the packaged ruleset schema, package version,
active-rule catalog, and deterministic ruleset digest.

Inspect and validate the packaged human-readable quality rules:

```shell
.venv/bin/sndocs quality validate
.venv/bin/sndocs quality list
.venv/bin/sndocs quality show SND-NAV-001
```

Rules live in `src/sndocs/quality_rules/rules/` as Markdown with strict YAML frontmatter. Start new
rules as drafts, define their requirement and applicability with passing and failing examples, and
register a tested detector before activating an automated rule. Detector implementation details
remain in Python. Rule IDs are permanent and retired IDs are never reused; contributor instructions
and lifecycle guidance are in `src/sndocs/quality_rules/README.md`.

Use the [UI remediation workflow](docs/ui-remediation.md) to triage a finding, choose the earliest
responsible layer, add a regression fixture, and select the correct diagnostic and release build.
Generated Markdown and HTML are never patched in place; one complete family is the smallest safe
rendering unit.

## Output contract

The assembled site contains:

- `index.html`, redirecting to the newest current family;
- `versions.json`, consumed by the Material release selector;
- schema-version-2 `link-report.json`, recording typed document and navigation repairs, generated missing-document placeholders, and omitted-image occurrences;
- `build-manifest.json`, containing the build profile, upstream SHAs, archive states, timestamps, and the pipeline fingerprint;
- `SERVICENOW-LICENSE.txt`, retaining upstream attribution and license information; and
- one directory per current or retained archived family, with a generated Material landing page at the family root.

Each current production-family directory also contains a `pagefind/` bundle. Smoke families omit
search, while retained archived families remain immutable and may contain their historical search
implementation.

Packaging creates `sndocs-site.tar.gz`, `sndocs-site.zip`, and a SHA-256 file for each archive.
The public packaging command and default full-current-family build remain available, but Cloudflare
publication follows the [latest-with-archives deployment policy](docs/deployment-runbook.md),
executed from an operator workstation with no CI (see
[ADR-0023](docs/adr/0023-publish-from-a-local-operator-workstation.md)). It builds only current
latest, stores immutable family and release objects in private R2, serves them through a
version-pinned Worker, and retains every family that was previously published as latest. The
rolling `site-artifact` GitHub Release remains a host-agnostic recovery channel, updated by the
operator through the same runbook.

## Configuration

Edit `pipeline.toml` to set the site identity, canonical site URL, upstream repository and
`llms.txt` path, optional family allowlist, and archive basename. Publication is intentionally
manual and operator-driven; the [runbook](docs/deployment-runbook.md) is the complete procedure.

## Licensing

Pipeline code is available under the repository's MIT license. Mirrored documentation remains
copyright ServiceNow and is redistributed under the upstream Apache License 2.0. Every generated
page links to its upstream source and, when provided, its official canonical documentation page.

© 2026 ServiceNow, Inc. All rights reserved.

ServiceNow, the ServiceNow logo, Now, and other ServiceNow marks are trademarks and/or registered
trademarks of ServiceNow, Inc., in the United States and/or other countries. Other company and
product names may be trademarks of the respective companies with which they are associated.

sndocs.com is an independent community mirror and is not affiliated with or endorsed by ServiceNow.
