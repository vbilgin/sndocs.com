# Remediating UI audit findings

`sndocs audit-ui` is diagnostic: it reads an assembled site and writes a separate report, but it does not repair pages, invoke a build, or make findings fatal. Keep the report directory separate from the audited site. The command rejects equal, nested, and parent output paths so `--clean` cannot alter the input site.

This workflow implements [ADR-0017](adr/0017-remediate-ui-findings-at-source.md).

## Triage before changing code

Start from the finding's stable rule ID, representative URL, detector context, severity, and confidence. The affected-page count shows whether the pattern is isolated or repeated; the representative is the fixture candidate. Confirm the observation before choosing its owner:

| Finding origin | Correct owner |
| --- | --- |
| Generated Markdown, link, title, or navigation defect | Transformation, link resolution, or navigation construction |
| Repeatable malformed upstream structure | Narrow deterministic normalization with an upstream-shaped fixture |
| Shared overflow, clipping, or interaction defect | Theme CSS, JavaScript, or template |
| Missing generated resource | MkDocs configuration, asset reference, or assembly |
| Detector false positive | Detector and detector fixture; leave the generated site unchanged |
| Browser startup, timeout, or environment problem | Audit setup or audit error handling; leave the generated site unchanged |

Fix the earliest responsible layer. Do not edit generated Markdown or HTML, and do not add a generic post-build repair pass. Preserve upstream wording and attribution; any recovery for malformed input must remain deterministic and auditable.

## Add a regression fixture

Reduce a confirmed observation to the smallest source structure that reproduces it. Test the earliest responsible transformation, navigation, link, theme, or assembly behavior, then add an audit-level assertion when it protects the detector-to-rule integration. Preserve existing rule IDs unless the semantic requirement itself changes.

A false-positive correction needs focused detector coverage and a rerun against the existing site. It does not require regenerated site output, even though a later build will observe the package-wide pipeline fingerprint change.

## Rebuild at family granularity

A complete release family is the smallest safe rendering unit. MkDocs navigation, search, shared assets, placeholders, and adjacent-page links can depend on more than the reported page, so affected generated files are never rebuilt or replaced individually.

For fast transformation, navigation, and general layout iteration, build one family with the smoke profile:

```shell
.venv/bin/sndocs build --output site-smoke --source ../ServiceNowDocs --smoke --family australia
.venv/bin/sndocs audit-ui --site site-smoke --output ui-report-smoke
```

Smoke omits search. Validate search or other production-only behavior with an isolated one-family production build:

```shell
.venv/bin/sndocs build --output site-diagnostic --source ../ServiceNowDocs --family australia
.venv/bin/sndocs audit-ui --site site-diagnostic --output ui-report-production
```

Do not package that diagnostic output. A production build intentionally treats families omitted by a per-run selection as archived when they are retained from `--reuse-from`; it is not a complete current-family release.

After accepting a rendering-pipeline correction, run the normal production build with every configured current family. The current package-wide pipeline fingerprint rebuilds all current families after implementation changes and retains already archived families unchanged.

## Verification

Run focused tests, then `.venv/bin/pytest`. Audit the affected family at both built-in viewports and confirm the targeted observation is absent without regressions in related rules. Search and production-asset corrections require a production-profile diagnostic. Before release, complete the all-family production build and strict artifact validation. If validation stops at a diagnostic family because a full build is intentionally deferred, record that skipped integration check and its remaining risk.
