# Project Context

Compact current-state handoff; use `.agent/WORKLOG.md`, ADRs, and Git history for historical detail.

## Objective

Build `sndocs.com`, an independent documentation mirror generated from `ServiceNow/ServiceNowDocs`. The pipeline discovers release families, transforms Markdown, builds versioned MkDocs Material sites, and packages the tree as host-agnostic GitHub Release artifacts.

## Current architecture

- `pipeline.toml` defines site identity, upstream repository, optional family allowlist, and artifact naming.
- `discovery.py` parses upstream `llms.txt`, preserves its family/publication ordering, and resolves release-branch SHAs.
- `source.py` provides remote and reusable-local source implementations; local sources discover and export exact family commits from clean remote-tracking refs without changing branches.
- `navigation.py` converts publication `index.md` hierarchies into MkDocs navigation and resolves their targets through the shared family link resolver.
- `transform.py` tolerates malformed YAML frontmatter, enriches pages, rewrites links, converts recognized upstream navigation tables into responsive linked cards, renders missing local images as omitted-image notices, and creates placeholders for unavailable content.
- `links.py` repairs stale same-family document and navigation links using exact paths, unique basenames, same-publication disambiguation, self-canonical metadata, and narrowly scoped reviewed fallback overrides; unresolved ambiguity is fatal.
- `builder.py` builds families independently with pruned navigation, writes directly to final family outputs, cleans automatic per-family work, hard-links reusable output when possible, retains removed families as archives, and assembles manifests and version metadata.
- `artifacts.py` validates the assembled site and creates ZIP/TAR archives with SHA-256 checksums.
- `.github/workflows/build-site.yml` runs scheduled or manual builds and publishes the rolling `site-artifact` GitHub Release when inputs change.

The `sndocs` 0.2 CLI manages reusable sources, discovery, side-effect-free build planning, production or selected-family smoke builds, validation, packaging, and local HTTP preview. It provides concise human or single-object JSON results and automatic GitHub Actions outputs.

## Important invariants and decisions

- Upstream `llms.txt` is authoritative for current families and publication ordering.
- Every current family is published under `/<family>/`; the root redirects to the newest.
- Deleted upstream families remain available as immutable archived snapshots.
- Publication indexes define navigation, but all Markdown files are rendered so inbound links remain valid.
- Same-family moved links are repaired when the destination is deterministic through path or self-canonical metadata, or selected by a family/source/target-specific reviewed fallback override.
- Missing upstream targets receive clearly marked diagnostic placeholder pages.
- Cross-family moved-link resolution is intentionally not attempted.
- MkDocs strict mode remains enabled; ambiguity and pipeline-created broken links fail.
- Production builds include every selected family and search; smoke manifests are distinct, omit search, and cannot be packaged.
- Existing build output requires explicit `--clean` replacement after discovery succeeds; dry runs never write or delete files.
- Automatic workspaces below ignored `.temp/` are bounded to one family and cleaned automatically; explicit `--work-dir` content is preserved.
- Source prose is preserved with light enrichment rather than editorial restructuring.
- Upstream media is not restored because ServiceNowDocs intentionally omits it.
- Generated Markdown and HTML stay out of the main branch.
- Topics use host-agnostic directory URLs (`/topic/` backed by `topic/index.html`); preview them over HTTP.
- Mirrored content retains ServiceNow's required trademark notice, a UTC build-year copyright notice, and its Apache-2.0 license notice; the site clearly states that it is independent and unaffiliated and links to the public ServiceNowDocs source repository.

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

- The initial Python/MkDocs pipeline, Material overrides, packaging, and release workflow are implemented.
- Malformed upstream YAML containing unquoted colons is handled with a conservative field-level fallback parser.
- Stale same-family links are repaired and genuinely missing targets receive placeholders.
- Incremental and archived builds retain link-resolution reports.
- Production navigation prunes inactive branches, family sites no longer have a duplicate temporary copy, and local source archives stream during extraction.
- The test suite currently reports 85 passing tests and one filesystem-specific skip on case-insensitive macOS.
- Australia SHA `71f4936` now passes a zero-warning render-free audit and a strict production build with 488 repaired navigation references, 67 missing navigation occurrences represented by placeholders, and 6 omitted-image occurrences across 3 targets.
- Production and smoke builds minify HTML while leaving inline JavaScript and CSS untouched; Australia output shrank by 46.4% in validation.
- Every family now receives a generated Material landing page at its manifest route, and artifact validation rejects missing family roots or unrewritten current-family raw Markdown links.
- Recognized upstream `nav-card` tables render as accessible adaptive card grids with clean directory links and descriptions recovered from omitted-icon alt text.

## Known gaps and risks

- GitHub Actions publication to the rolling Release has not yet been proven in production.
- Full families remain large (Australia alone contains roughly 49,000 Markdown files and generates 4.03 GiB), making complete artifacts and browser-side search expensive despite bounded temporary storage.
- Navigation usability and Material search performance still need browser evaluation against a successful complete site.
- Australia contains 20 stale-anchor diagnostics at MkDocs' informational level; anchor validation intentionally remains informational.
- Cross-family links can still become stale when equivalent topics move between directories in different release branches.

## Next likely work

1. Inspect Australia's navigation, placeholder pages, release selector, and search behavior in a browser.
2. Attempt the complete multi-family build and measure final artifact and browser search performance.
3. Exercise the GitHub Actions workflow and verify rolling Release reuse and publication.

## Development and verification

```shell
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e '.[test]'
.venv/bin/pytest
.venv/bin/sndocs discover
.venv/bin/sndocs build --output site
.venv/bin/sndocs validate --site site
.venv/bin/sndocs package --site site --destination artifacts
```

Use `upstream.families` in `pipeline.toml` to restrict local experimental builds. Before trusting this document over the repository, inspect current Git status, recent commits, configuration, and relevant tests.
