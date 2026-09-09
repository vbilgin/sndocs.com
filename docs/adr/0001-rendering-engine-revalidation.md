# ADR 0001 — Rendering-engine re-validation and the `pymdownx` bundle

Status: accepted (issue #14, v1-completeness gate)
Date: 2026-09-08

## Context

The normalizer (`sndocs.normalize`) treats a cleanup as safe to apply only when
it is **render-equivalent** — but it checks that with `markdown-it-py`
(CommonMark preset + `table` + `strikethrough`), which is *not* the engine that
renders the site. `mkdocs build` renders with **Python-Markdown** plus whatever
`markdown_extensions` `mkdocs.yml` declares. Issue #14 (parent user story 30)
requires confirming the normalizer's "safe to normalize" guarantees actually
hold under that real engine, and tuning the `pymdownx` bundle until rendering
matches expectations.

Before this work `mkdocs.yml` declared **no** `markdown_extensions` at all, so
MkDocs fell back to its three built-ins: `toc`, `tables`, `fenced_code`.

## What was checked

Against the **real pipeline** (`sndocs fetch` → `sndocs normalize` on the full
`australia` corpus, 50,112 Markdown files; rendering through the real `mkdocs.yml`
+ MkDocs + Material + Python-Markdown):

1. **`sndocs.engine_check` sweep** — for every file, renders the source body and
   the normalized body through the configured Python-Markdown engine and flags a
   `cosmetic-divergence` (the normalizer's cleanup gate passes under
   `markdown-it-py` but the real engine renders the cleaned body differently,
   beyond known-benign stray-backslash removal and insignificant whitespace) or
   a `table-not-rendered` (the normalized body strands a pipe-table delimiter
   row in prose). Run over random samples totalling >16,000 files across three
   seeds (`python -m sndocs.engine_check --sample N --seed S`); a full-corpus run
   is supported but slow because the largest API pages render 3–4× each.
2. **Rendered-output pathology scan** over all 50,112 normalized files: literal
   ```` ``` ```` fence markers surfacing in `<p>`, pipe-table delimiter rows
   leaking into prose, stray `\(` / `\)` / `\_` backslashes surviving into the
   rendered HTML.
3. **Manual spot-check** of 15 pages through an actual `mkdocs build` (real
   `mkdocs.yml`): the five issue-#14 fixtures —
   `c_GlideSystemAPI.md`, `devops-api.md`, `change-management-api.md`,
   `product-catalog-open-api.md`, `ap-invoice-api.md` — plus ten samples chosen
   to exercise heavy escape-removal inside raw HTML tables, simple-table
   conversion, fence-heavy pages, a malformed pipe table, a fence abutting a raw
   HTML block, ordinary prose with cross-page links, a large TOC page, and the
   front-matter fallback path.

## Findings

### 1. Stock `fenced_code` leaves many code fences as literal text — FIXED via config

`fenced_code` does not recognise a fenced block that is indented as list-item
continuation — the pattern the corpus's how-to steps use constantly:

```
1.  Add the script:

    ```
    var x = 1;
    ```
```

`markdown-it-py` renders that as a code block; `fenced_code` leaves the
```` ``` ```` markers as literal `<p>```</p>` text and renders the code as an
ordinary (and mangled) paragraph. The rendered-output scan found a
literal-fence-in-`<p>` on ~195 pages.

**Resolution:** add `pymdownx.superfences`. MkDocs still lists `fenced_code` (its
built-in), but superfences registers ahead of it and takes over fence
processing. Re-scan after the switch: ~195 → 9 residual (see finding 3). A 3,000-page
before/after diff found 0 real regressions — the only apparent "lost tables"
were spurious `<table…>`-looking placeholders in code samples that `fenced_code`
had failed to capture and superfences correctly keeps inside `<pre>`.

`pymdownx.highlight` (`guess_lang: false`) is added as the documented superfences
pairing; it does not change structure for unlabelled fences.

### 2. Redundant escapes inside raw HTML tables render literally — NOT config-fixable

Python-Markdown's core HTML-block parser is greedier than CommonMark /
`markdown-it-py`: it keeps a `<table>…</table>` block (and the
blank-line-separated Markdown-looking text between its cell tags) as opaque raw
HTML, so backslash escapes inside it are **not** resolved and a literal `\(`,
`\)` or `\_` reaches the page. `markdown-it-py` instead ends the HTML block at
the first blank line and parses the cell text as Markdown, resolving the escape
— which is why the normalizer's markdown-it render-equivalence gate never saw a
difference here.

The normalizer compounds this: `cosmetic_candidate()` suppresses its
redundant-escape removal while `in_table` (between `<table` and `</table>`), so
these escapes are never cleaned in the first place.

Scale: **8,027 / 50,112 rendered pages (16%)** carry at least one visible stray
backslash; 867 pages carry 50+; the worst (API-reference pages such as
`servicecontract-api.md`, `case-api.md`) exceed 4,000. This materially degrades
the most-used section of the docs.

Not fixable by `pymdownx` config: `md_in_html` was tested and has **no effect**
(it only descends into HTML elements that opt in with a `markdown` attribute,
which the corpus's tables do not have), and no extension makes the core
HTML-block parser blank-line-terminated. `md_in_html` is also undesirable here —
it would start reinterpreting genuine raw-HTML content across the ~34k tables the
normalizer deliberately leaves as raw HTML.

**Recommended follow-up (normalizer change, its own ticket):** relax the
`in_table` guard in `cosmetic_candidate()` so redundant-escape removal
(`\(`→`(`, `\)`→`)`, `\_`→`_` between word characters) also runs inside raw HTML
tables. Those three substitutions cannot alter HTML table structure and are
render-neutral under `markdown-it-py` and an improvement under Python-Markdown;
the change stays protected by the existing whole-file markdown-it
render-equivalence gate. It needs its own re-validation pass (idempotence across
the full corpus) so it is out of scope for this ticket.

### 3. Residual pre-existing malformed source — NOT config-fixable

* **~18 pages**: pipe tables whose column counts don't line up or that carry a
  single-column caption row above the header. `markdown-it-py`'s lenient GFM
  table parser renders them as tables; Python-Markdown's stricter `tables`
  extension does not, and the delimiter row leaks into a `<p>` (e.g.
  `r-Sybase.md`). No `pymdownx` extension offers a more lenient table parser.
* **~9 pages**: a ```` ``` ```` fence directly abutting a raw HTML block with no
  blank line (e.g. `t_CreateAPowershellActivity.md`). The normalizer's
  `repair_table_boundaries()` only inserts a blank line when `</table>` is
  followed by a fence *on the same line*; a newline-then-fence slips through.

Both are pre-existing source defects, not introduced by normalization, and
affect ~0.05% of the corpus. Recommended follow-up: widen
`repair_table_boundaries()` for the fence case; consider a targeted
malformed-pipe-table repair for the first.

### 4. Out of band: full-corpus `mkdocs build` does not complete in practical time

Not a rendering-correctness issue, so not addressed here, but surfaced by this
work: an isolated subtree builds at ~44 pages/s (~19 min extrapolated), but a
real full build slows to ~0.2 pages/s because Material renders the entire
50k-entry nav into every page (O(n²)). `sndocs build` / `sndocs all` therefore
don't finish in practice on the full corpus. Recommended follow-up: its own
ticket (nav strategy — `navigation.prune`, section-index pages, or splitting the
build).

### 5. `sndocs normalize` reports 33 idempotence failures on the full corpus

Pre-existing, unrelated to the engine: 33 files fail the normalizer's own
"normalization is not idempotent" invariant (all under
`api-reference/cllent-mobile-api-reference/` and
`api-reference/server-api-reference/`). Recorded here only because it surfaced
during the full-pipeline run; belongs to the normalizer (issue #8 area).

## Decision

`mkdocs.yml` `markdown_extensions`:

```yaml
markdown_extensions:
  - tables
  - toc:
      permalink: true
  - pymdownx.superfences
  - pymdownx.highlight:
      guess_lang: false
```

Rationale, kept deliberately close to the normalizer's `markdown-it-py`
CommonMark + `table` baseline:

* **`tables`** — the corpus is full of GFM pipe tables and the normalizer emits
  them when converting simple HTML tables.
* **`toc` (`permalink: true`)** — heading anchors for in-page navigation.
* **`pymdownx.superfences`** replaces stock `fenced_code` (finding 1).
* **`pymdownx.highlight` (`guess_lang: false`)** — documented superfences
  pairing; an unlabelled fence stays a plain `<pre><code>`.

Deliberately **not** enabled:

* **`md_in_html`** — raw HTML must stay opaque passthrough, matching
  `markdown-it-py`'s `html: true` and the normalizer's "leave complex tables as
  raw HTML" contract (finding 2).
* **the aggressive inline-syntax extensions** (`pymdownx.tilde`, `caret`,
  `mark`, `smartsymbols`, `magiclink`, `emoji`, `keys`) — near-zero corpus usage
  (`~~strikethrough~~` appears in 3 files of 50,112) and every one widens the
  parse surface the normalizer's render-equivalence guarantees rest on, with a
  real risk of mangling API-doc content (`~`, `^`, `==`, `(c)`, `::`).

## Consequences

* The normalizer's render-equivalence-gated **cosmetic cleanup** and
  **simple-table conversion** are confirmed to hold under the real engine. Across
  the samples the sweep's only hits were `cosmetic-divergence` at ≈0.06%
  (≈5 per 8,000 files) and zero `table-not-rendered`. Every `cosmetic-divergence`
  was checked by hand and is **visible-text-identical** — the difference is HTML
  block-serialisation whitespace (newline placement between `</p>`, `<li>`,
  `<table>` around raw HTML blocks), not content or DOM structure. No case where
  cleanup makes rendering *worse*; the one class where it would make it *better*
  is finding 2, which the normalizer currently declines to do.
* `tests/test_engine_check.py` pins the bundle and the superfences fix as a
  regression guard; `python -m sndocs.engine_check` re-runs the full sweep.
* Findings 2–5 are logged as follow-up work and do **not** block v1 on the
  rendering-engine axis this ticket gates.
