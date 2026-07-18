# Project Context

Compact handoff document for contributors and agents. Keep this file focused on current state; use `.agent/WORKLOG.md`, ADRs, and Git history for historical detail.

## Objective

Build `sndocs.com`, an independent community documentation mirror generated from the public `ServiceNow/ServiceNowDocs` repository. The pipeline discovers ServiceNow release families, transforms their Markdown, builds versioned MkDocs Material sites, and packages the complete static tree as host-agnostic GitHub Release artifacts.

## Current architecture

- `pipeline.toml` defines site identity, upstream repository, optional family allowlist, and artifact naming.
- `discovery.py` parses upstream `llms.txt`, preserves its family/publication ordering, and resolves release-branch SHAs.
- `source.py` provides remote and reusable-local source implementations; local sources discover and export exact family commits from clean remote-tracking refs without changing branches.
- `navigation.py` converts publication `index.md` hierarchies into MkDocs navigation.
- `transform.py` tolerates malformed YAML frontmatter, enriches pages, rewrites links, renders omitted-image notices, and creates placeholders for unavailable content.
- `links.py` repairs stale same-family links using exact paths, unique basenames, same-publication disambiguation, self-canonical metadata, and narrowly scoped reviewed fallback overrides; unresolved ambiguity is fatal.
- `builder.py` builds families independently with pruned navigation, writes directly to final family outputs, cleans automatic per-family work, hard-links reusable output when possible, retains removed families as archives, and assembles manifests and version metadata.
- `artifacts.py` validates the assembled site and creates ZIP/TAR archives with SHA-256 checksums.
- `.github/workflows/build-site.yml` runs scheduled or manual builds and publishes the rolling `site-artifact` GitHub Release when inputs change.

The public CLI is `sndocs` with `discover`, `build`, `validate`, and `package` commands. `discover` and `build` accept `--source-repo`, `--clone-source`, and explicit `--refresh-source` inputs for fast offline testing; `build --smoke` strictly renders only the newest family without search.

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
- Automatic workspaces live under ignored `.temp/`, are bounded to one family's source/transformed Markdown, and are cleaned automatically; explicit `--work-dir` content is preserved.
- Source prose is preserved with light enrichment rather than editorial restructuring.
- Upstream media is not restored because ServiceNowDocs intentionally omits it.
- Generated Markdown and HTML stay out of the main branch.
- Mirrored content retains ServiceNow attribution and its Apache-2.0 license notice; the site clearly states that it is independent and unaffiliated.

## Artifact contract

The assembled site contains:

- one directory for each current or archived family;
- `index.html` redirecting to the newest family;
- `versions.json` for the release selector;
- `build-manifest.json` with source SHAs, archive state, build profile, pipeline fingerprint, and link counts;
- `link-report.json` with per-family link repairs and missing-document placeholders; and
- `SERVICENOW-LICENSE.txt`.

Packaging produces `sndocs-site.tar.gz`, `sndocs-site.zip`, and SHA-256 files for both.

## Current status

- The initial Python/MkDocs pipeline, Material overrides, packaging, and release workflow are implemented.
- Malformed upstream YAML containing unquoted colons is handled with a conservative field-level fallback parser.
- Stale same-family links are repaired and genuinely missing targets receive placeholders.
- Incremental and archived builds retain link-resolution reports.
- Production navigation prunes inactive branches, family sites no longer have a duplicate temporary copy, and local source archives stream during extraction.
- The test suite currently reports 52 passing tests and one filesystem-specific skip on case-insensitive macOS.
- Live discovery previously confirmed Australia, Zurich, Yokohama, and Xanadu branches.
- A measured Australia production attempt bounded the automatic workspace at 698 MiB on disk and generated 4.1 GiB of HTML with a 227 MiB search directory before strict validation rejected 494 upstream navigation, missing-image, and stale-anchor warnings.
- Durable architectural decisions are recorded under `docs/adr/`.
- Repository-wide agent operating and context-maintenance instructions are established in root `AGENTS.md`.

## Known gaps and risks

- A complete family build remains blocked by 494 strict MkDocs warnings from malformed/missing navigation targets, omitted image links, and stale anchors in the Australia upstream snapshot.
- GitHub Actions publication to the rolling Release has not yet been proven in production.
- Full families remain large (Australia contains roughly 49,000 Markdown files and generated 4.1 GiB before strict failure), making final artifacts and browser-side search expensive despite bounded temporary storage.
- Navigation usability and Material search performance still need browser evaluation against a successful complete site.
- Cross-family links can still become stale when equivalent topics move between directories in different release branches.

## Next likely work

1. Reconcile Australia's deterministic upstream navigation, missing-image, and stale-anchor warnings with strict-build policy.
2. Complete a clean Australia build, then validate `link-report.json`, placeholders, version switching, navigation, and search.
3. Attempt the complete multi-family build and measure final artifact and browser search performance.
4. Exercise the GitHub Actions workflow and verify rolling Release reuse and publication.

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
