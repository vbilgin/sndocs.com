# ADR-0015: Audit generated UI with a local hybrid scanner

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** Victor Bilgin
- **Related commit:** `dc50551` — `Add local hybrid UI audit`

## Context

Strict MkDocs validation and assembled-site checks detect invalid source and link structures but do not detect presentation defects such as Markdown syntax exposed inside tables, duplicated visible navigation entries, or viewport overflow. A production family contains tens of thousands of pages, making a browser-only crawl too expensive for routine local diagnosis.

## Decision

Provide a report-only `sndocs audit-ui` command for completed production or smoke sites. Scan every generated HTML file with a deterministic structural audit, then use Chromium to render one representative for each deduplicated high-risk pattern plus a seeded sample at desktop and mobile viewports.

Publish a schema-versioned JSON report, a browsable HTML summary, and screenshots only for rendered findings. Findings never fail the command; invalid input, missing browser installation, or an audit that cannot start remain errors. Preserve existing reports unless replacement is explicitly requested with `--clean`.

Keep Playwright in an optional `ui` dependency group, keep reports untracked, and do not add the audit to build, validation, packaging, scheduled publication, or CI workflows in this initial version.

## Consequences

- Every page receives inexpensive structural coverage while browser cost remains bounded and reproducible.
- Reports group repeated defects by stable rule and context, retain affected-page counts, and provide representative visual evidence.
- Developers must install Playwright and its Chromium runtime before using the command.
- The tool identifies transformation and navigation defects but does not modify generated output or source transformations.

## Alternatives considered

- **Render every production page:** Rejected because the runtime and resource cost are disproportionate for routine local use.
- **Use only static HTML checks:** Rejected because layout, visibility, console, and viewport defects require a browser.
- **Gate scheduled publication or CI:** Deferred until the rules and false-positive rate have been proven against production output.
