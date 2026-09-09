# ADR 0002 — HTML minification of the built site, on by default

Status: accepted (issue #34, parent #31; ADR 0001 follow-up)
Date: 2026-09-09

## Context

`sndocs build` renders the normalized `australia` corpus (50,112 Markdown files)
into `.sndocs/site/`. After ADR 0001's `navigation.prune` fix the render
completes in practical time, but the output is large: a full-corpus build is
**≈11.5 GiB on disk**, and the rendered HTML is almost all of it (**11.94 GB
across 50,113 `*.html` pages**; Material's shared `assets/` bundle and the
Pagefind index are the small remainder). Every `sndocs build` / `sndocs all`
run rewrites that tree from scratch, and the repo commits no corpus, so each
contributor who runs the pipeline pays the full footprint locally. Shrinking the
on-disk site is the primary driver here; forward-looking hosting / artifact
portability is a secondary benefit. This is not a v1 user story — it is the
deferred "HTML minification" follow-up recorded at the end of ADR 0001, in the
same post-v1 family as #25/#26/#27.

ADR 0001's finding-4 work measured one minification route and rejected it:
`mkdocs-minify-plugin` (which wraps `htmlmin2`) shaves ~46% off the rendered
HTML but runs **single-threaded, in-process, at ~50 pages/s** — roughly
**+16 min** on the full corpus, which pushed `sndocs build` well past the
single-digit-minute target that ticket existed to hit. It was left as "its own
optional-flag / faster-minifier follow-up". Issue #31 is that follow-up;
#32 (the pass, opt-in), #33 (the checker), and #34 (this ADR + the default
flip) are its children.

## Decision

Adopt a **parallel post-build HTML minification pass** and make it the default.

1. **`minify-html`, not a MkDocs plugin.** `minify-html` is Rust-backed with
   prebuilt wheels for CPython 3.10–3.14 on every platform this runs on. The
   pass is a plain `.sndocs/site/**/*.html` walk inside `build_site()`, between
   the MkDocs render and Pagefind indexing (the `pagefind/` directory does not
   exist yet, so the walk needs no exclusions), parallelised across a
   `ProcessPoolExecutor` sized by `--minify-workers` (default: CPU count) —
   mirroring the `sndocs normalize` fork-context + per-worker-globals pattern.
   A file that raises is left byte-for-byte as MkDocs produced it, tallied, and
   reported; the build still exits 0. A file is rewritten only when
   minification actually shrinks it.

2. **A deliberately conservative minify profile**, defined once as
   `sndocs.minify.MINIFY_OPTIONS` and imported by `sndocs.minify_check` (never
   re-declared). Every keyword `minify-html` accepts is pinned explicitly, even
   where the value matches today's library default, so a future release that
   flips a default cannot silently change the built site
   (`test_minify_options_are_the_conservative_profile` locks the exact dict):

   - `keep_closing_tags=True`, `keep_html_and_head_opening_tags=True` — leave
     the tag shape MkDocs emitted intact; only inter-element whitespace and
     comments go.
   - `keep_comments=False` — strip HTML comments (the library default). Safe
     here: the pass runs *before* Pagefind indexing and neither the corpus nor
     the theme uses an HTML-comment Pagefind directive; if that ever changes,
     switch to the `data-pagefind-ignore` attribute form.
   - `minify_css=False`, `minify_js=False` — never touch stylesheet or script
     bodies (the inline `PagefindUI(...)` bootstrap is left exactly as
     rendered).
   - `minify_doctype=False`, and **every `allow_*` relaxation off** — in
     particular `allow_optimal_entities=False`, so an `href` query string like
     `?x=1&sect=2&para=3` is never re-parsed into `§`/`¶`.

3. **Default on.** `sndocs build` and `sndocs all` minify unless `--no-minify`
   is passed. `--minify-workers N` has no effect without minification, so
   `--no-minify --minify-workers N` is a usage error. `build_site(minify=...)`
   keeps `False` as its library default; only the CLI surface defaults on.

The conservative profile still collapses whitespace-only text nodes and drops
attribute quotes where the value doesn't need them (`href="../x/"` →
`href=../x/`). Both are serialisation changes that leave the parsed DOM
identical — see Consequences.

## Rejected alternatives

- **The `mkdocs-minify-plugin` / `htmlmin2` route** (ADR 0001 finding 4):
  single-threaded, in-process, ~50 pages/s, ~+16 min on the full corpus. The
  parallel `minify-html` walk gets the same class of size saving in **~20 s**
  (see Consequences).
- **`minify_css=True` / `minify_js=True`.** Would rewrite Material's stylesheet
  and the inline Pagefind bootstrap. Out of proportion to the footprint they
  represent (the HTML dominates), and every byte changed inside a `<script>` or
  `<style>` widens the surface the "rendered pages stay semantically identical"
  guarantee has to cover.
- **Aggressive entity / attribute modes** (`allow_optimal_entities`,
  `minify_doctype`, `allow_noncompliant_unquoted_attribute_values`,
  `allow_removing_spaces_between_attributes`). `allow_optimal_entities` is the
  concrete hazard: it decodes semicolon-less named-entity prefixes, and the
  corpus's API-doc URLs carry query params (`&sect=`, `&para=`) that are exactly
  such prefixes. The rest buy little and each is a small correctness risk on a
  corpus this varied.
- **Keeping HTML comments** — no benefit here; the theme/corpus carry no
  meaningful ones, and stripping them is part of the saving.
- **gzip / brotli precompression.** Explicitly a *future* layer, applied
  *after* minification (minify first, then compress the smaller bytes), and out
  of scope for this ADR. Precompression shrinks bytes-at-rest / bytes-on-the-wire
  without changing the HTML the browser parses; minification shrinks the HTML
  itself. They compose; this ticket does the second one only. Its own ticket
  when hosting is in scope.

## Consequences

### Measured, full corpus

Full normalized `australia` corpus (50,112 files → 50,113 rendered `*.html`
pages) through the real `mkdocs.yml` + Material + `navigation.prune`, on a
10-core machine, minifying at the default worker count (`--minify-workers` = 10):

| | `--no-minify` | minified (default) |
| --- | --- | --- |
| `.sndocs/site/` on disk | 12,039,200 KiB (≈11.5 GiB) | 6,683,920 KiB (≈6.4 GiB) |
| rendered HTML | 11,938,728,502 B (11.94 GB) | 6,454,495,892 B (6.45 GB) |

- **On-disk reduction: 44.5%** of the whole `.sndocs/site/` tree
  (**45.9%** of the rendered HTML considered on its own — 5.48 GB saved).
- **Added wall-time: ≈20 s** for the minify pass over all 50,113 pages at
  10 workers. The baseline full `sndocs build` (render + Pagefind) is ~705 s;
  the minify pass adds ~3% to that, versus the ~+16 min the rejected plugin
  route cost for the same size class.
- **Per-file failures: 0** across all 50,113 pages (a failure would leave that
  file's original bytes in place, be tallied, and be reported; exit code stays
  0).

### `sndocs.minify_check` is the standing guard

`python -m sndocs.minify_check --sample N --seed S` (issue #33) is the committed,
re-runnable verification tool — sibling of `sndocs.engine_check`. It imports the
*same* `MINIFY_OPTIONS`, minifies each sampled page, and asserts five strict
invariants between original and minified: tag-structure identity, collapsed
text-content identity, byte-identical `href`/`src` values, structurally
identical inline `<svg>` subtrees, and entity-decoded `<pre>` text identity.
Only inter-element whitespace text nodes may differ; anything else exits
non-zero.

Run over 3 samples of 3,000 pages of this build (seeds 0–2, 9,000 pages), it
reports:

- **Zero** `text-content`, `link-attr`, `inline-svg`, `pre-text` or
  `parse-failure` divergences. Visible text, every link, every code block and
  every inline SVG are byte-identical after minification.
- **45 `tag-structure` divergences (≈0.5% of sampled pages)**, all of one
  pre-existing class — see below.
- Aggregate size reduction 45.9–46.0% per sample, matching the full-corpus
  figure.

This clears the two `minify-html` correctness risks surfaced during the #31
grilling:

- **Issue #192** (self-closing inline `<svg>` emitted unclosed, re-parenting
  everything after it) — the `inline-svg` check compares each `<svg>` subtree's
  structure; a re-parent shows up as an `inline-svg` (and `tag-structure`)
  divergence. Zero seen.
- **Issue #169** (named-entity-prefix query params like `?x=1&sect=2` decoded
  to a character) — the `link-attr` check compares every `href`/`src` value as
  parsed. `allow_optimal_entities` is off so no decode happens; zero seen, and
  the check would catch a future regression.

### Known: `tag-structure` divergence on malformed raw-HTML-table source

The 45 `tag-structure` divergences (≈0.5%, ≈250 pages full-corpus) are all the
same pre-existing defect, **not introduced by minification**:

The corpus has raw HTML `<table>` blocks containing literal, unescaped
angle-bracket placeholder tokens — e.g.
`` `https://<instance name>.service-now.com/<Path>.do` `` in a cell, or
`<sys_id>`, `<specific_error_message>`, `<table_name>` in an example. Because
Python-Markdown keeps a `<table>…</table>` block as opaque raw HTML (ADR 0001
**finding 2**), those tokens reach the page as **bogus HTML elements**
(`<instance>`, `<path>`, `<sys_id>`, …). The **un-minified page already
contains them**. What minification changes is only *which libxml2 error-recovery
path* fires: removing the whitespace between a bogus `<Path>` and the next
`<tr>` flips libxml2 from "auto-close the bogus element, resume the table" to
"nest the rest of the table inside it", so the *recovered* tree shifts depth /
re-parents. In every case the checker confirms `text-content`, `link-attr`,
`pre-text` and `inline-svg` are unchanged, and a real browser (with its own,
more consistent recovery) renders both versions equally — the source is already
malformed either way.

This is accepted, with eyes open, because:

- it is a **serialisation-recovery difference on already-broken markup**, with
  no change to visible text, links, code or SVG, and no rendered-output
  regression versus the un-minified page;
- it belongs to ADR 0001 **finding 2** (redundant/!escaped content in raw HTML
  tables), tracked as **#26**; once that cleanup escapes or removes the
  placeholder tokens, `minify_check` goes clean on these pages with no further
  work here;
- `minify_check` remains the standing guard for every *other* class — a real
  re-parent, a dropped element, a decoded entity, `<pre>` whitespace loss,
  an unclosed SVG — none of which appear.

`minify_check` still exits non-zero when it sees these, by design; treat a
non-zero exit whose divergences are **only** this class (bogus-element subtree,
identical text/link/pre/svg) as expected until #26 lands, and any *other*
divergence as a real regression to stop on.

### Other

- Attribute quotes are dropped where the value doesn't need them
  (`href="../x/"` → `href=../x/`); the parsed DOM is unchanged, and
  `minify_check`'s `link-attr` check compares parsed values, not raw bytes. CLI
  tests that previously matched a quoted attribute literally were updated to
  match either serialisation.
- `--no-minify` remains a first-class opt-out for anyone who wants the raw
  MkDocs bytes (debugging a render, diffing template output).
- The Markdown in `.sndocs/normalized/` is untouched — the normalizer's
  formatting guarantees are unaffected.
- ADR 0001's trailing "HTML minification" paragraph is replaced with a pointer
  here.

## Follow-ups

- **#26** (ADR 0001 finding 2) removes the unescaped placeholder tokens that
  cause the `tag-structure` divergence class above; after it, `minify_check`
  should report fully clean.
- **gzip / brotli precompression** of the minified site — its own ticket when
  hosting is in scope.
