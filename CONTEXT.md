# CONTEXT

Glossary for the sndocs project. When code, issues, ADRs, tests, or UI text
name one of these concepts, use the term as defined here — don't drift to
synonyms.

## Glossary

### release family

A named ServiceNow release line (e.g. **Australia**, Washington DC, Xanadu).
ServiceNow publishes documentation per release family. v1 of sndocs targets the
**Australia** release family only, sourced from the `australia` branch of the
[upstream](#upstream) repository. "Release family" is the term the UI and docs
use; avoid "version", "release branch", or "channel" for this concept.

### corpus

The complete set of Markdown documentation files for one [release
family](#release-family), as published by [upstream](#upstream) — roughly 50,000
files for Australia. "The corpus" without qualification means the Australia
corpus. It refers to the document set as a whole, at whatever stage
(`.sndocs/repo/` after fetch, `.sndocs/normalized/` after normalize); when the
stage matters, say "the fetched corpus" or "the [normalized](#normalized-markdown)
corpus".

### upstream

The [ServiceNow/ServiceNowDocs](https://github.com/ServiceNow/ServiceNowDocs)
GitHub repository — ServiceNow, Inc.'s own publication of its product
documentation as Markdown, licensed Apache-2.0. It is the single source sndocs
fetches from; sndocs neither writes to it nor forks its content. "Upstream"
always means this repository, never a Git remote in general.

### normalized Markdown

[Corpus](#corpus) Markdown after `sndocs normalize` has applied its mechanical,
render-preserving cleanups (fence repair, escape removal, table repair, link
rewriting, …) and written the result to `.sndocs/normalized/`. The
transformation is deliberately limited to changes that leave the rendered
output equivalent — no editorial change, no content added or removed. Contrast
with the raw fetched Markdown in `.sndocs/repo/`.

### sndocs

The project. Two things share the name, disambiguate when it is not clear from
context:

- **sndocs (the CLI)** — the `sndocs` Python console command in this
  repository: `fetch`, `normalize`, `build`, `serve`, `all`. This repo is the
  CLI and its config; it holds no [corpus](#corpus) and no built output.
- **sndocs (the site)** — the static documentation site the CLI produces from
  the [normalized](#normalized-markdown) corpus (MkDocs + Material for MkDocs),
  served locally from `.sndocs/site/`. It presents under the lowercase wordmark
  **sndocs** and is an independent, unendorsed mirror of ServiceNow's
  documentation — not affiliated with, endorsed by, or sponsored by ServiceNow,
  Inc.
