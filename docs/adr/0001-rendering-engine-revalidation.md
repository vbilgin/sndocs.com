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
* Findings 2–5 are logged as follow-up work (see **Follow-up tickets** below).
  This ticket gates only the **rendering-engine axis** — whether the
  normalizer's render-equivalence guarantees hold under Python-Markdown — and on
  that axis all five findings are resolved or benign.
* Findings 2 and 3 (redundant escapes in raw HTML tables; residual malformed
  table/fence boundaries) are genuine post-v1 **rendering-quality** improvements
  and block nothing.
* Findings 4 and 5, however, do gate parent #5 on a **separate axis** this ADR
  does not otherwise cover: *the pipeline running end-to-end on the full
  `australia` corpus*. Finding 5 makes `sndocs normalize` exit non-zero on the
  real corpus (batch failure on 33 idempotence violations); finding 4 makes
  `sndocs build` / `sndocs all` never complete on it. Both are tracked as
  blocking sub-issues of #5.

## Follow-up tickets

| Finding | Issue | Gates #5? | Disposition |
| --- | --- | --- | --- |
| 2 — redundant escapes inside raw HTML tables | #26 | no | post-v1 rendering-quality; normalizer change, relax the `in_table` guard for `\(` `\)` `\_` only, plus a full-corpus idempotence re-validation pass |
| 3 — residual malformed table/fence boundaries | #27 | no | **resolved (code)** — `repair_table_boundaries()` widened for newline-then-fence (3b) and for the single-column-caption pipe-table shape (3a); see "Follow-up: finding 3" below. Full-corpus re-scan + idempotence re-validation still to run. |
| 4 — full-corpus `mkdocs build` does not complete (O(n²) nav) | #25 | **yes** (blocking) | **resolved** — `navigation.prune` (see "Follow-up: finding 4" below); render ~9 min, ~11 min end-to-end with Pagefind |
| 5 — 33 normalizer idempotence failures on the full corpus | #24 | **yes** (blocking) | pre-existing normalizer bug (issue #8 area), scoped to `api-reference/cllent-mobile-api-reference/` and `api-reference/server-api-reference/` |

Findings 2 and 3 are not sub-issues of #5 — they are standalone quality
follow-ups. Findings 4 and 5 are blocking sub-issues of #5.

## Follow-up: finding 3 — residual malformed table/fence boundaries (issue #27)

Date: 2026-09-09

Two conservative repairs added to `repair_table_boundaries()` in
`src/sndocs/normalize.py`, both idempotent and covered by the normalizer's
existing "no broken table boundary remains" invariant:

* **3b — newline-then-fence.** A ```` ``` ```` / `~~~` fence on the line
  *directly after* a `</table>` (previously only the same-line case was
  repaired) now gets a blank line inserted, so Python-Markdown renders it as a
  code block instead of leaking the fence markers into a `<p>`. The fence's own
  ≤3-space indent is preserved; a 4-space indented block after `</table>` is
  left alone (it is genuinely indented code, not a fence).
* **3a — single-column caption row.** A lone non-delimiter `| caption |` row
  sitting at a block boundary immediately above a multi-column
  `header + delimiter` pair (column counts matching) gets a blank line inserted
  between it and the header, so Python-Markdown's `tables` extension renders the
  table below (markdown-it-py already treats them as two blocks). The caption
  itself is left as prose — beautifying it would be guessing. **Other ragged
  shapes are deliberately not touched:** a header/delimiter column-count
  mismatch renders as prose under *both* engines, so there is no non-guessing
  repair and the normalizer leaves it exactly as-is. Body-row column
  raggedness already renders fine under Python-Markdown and needs no repair.

Unit coverage: `tests/test_normalize_table_repair.py`. **Still outstanding**
(needs the full corpus, run manually): re-scan the ~9 fence / ~18 pipe-table
pages with `python -m sndocs.engine_check` to confirm the leaks are gone, and a
full-corpus `sndocs normalize` idempotence pass (byte-identical second run).

## Follow-up: finding 4 resolved — `navigation.prune` (issue #25)

Date: 2026-09-09

**Cause confirmed.** With `nav:` computed from the ~50k-file corpus and no nav
feature set, Material renders the *entire* nav tree into every page's sidebar.
Each rendered page is ~18 MB (the abandoned `.sndocs/site/` from the #14 run has
155 pages at ~18 MB each = 2.7 GB); throughput collapses to ~0.2 pages/s, so a
full build is ~69 h extrapolated and never finishes in practice.

**Strategies measured** against the real normalized `australia` corpus (50,112
files) through the actual `mkdocs.yml` + Material, timing the MkDocs render only
(Pagefind excluded), on a 10-core machine:

| Strategy | Full-corpus build | Throughput | Output size | Avg page | Biggest page |
| --- | --- | --- | --- | --- | --- |
| none (baseline) | ~69 h (never completes) | ~0.2 pages/s | ~900 GB extrapolated | ~18 MB | ~19 MB |
| **`navigation.prune`** | **~9.0 min** (+27 s nav walk) | **92.9 pages/s** | 11.9 GB | 238 KB | 1.7 MB (`api-reference/`) |
| `navigation.prune` + HTML minify (`mkdocs-minify-plugin`) | ~25 min | — | ~6.4 GB (−46%) | ~128 KB | — |

Per-page size with prune: site root 18 MB → 39 KB (≈460×), a deep API page
18 MB → 154 KB (≈117×). Section-index pages stay larger in proportion to their
own direct child count — `api-reference/index.html` is 1.7 MB because that one
directory has ~1,250 sibling pages that legitimately belong in its section nav;
prune cannot and should not hide a section's own children on that section's page.

The ticket lists section-index pages and a split build as further candidates to
"measure each", but its own Notes say to reach for them only *after* confirming
`navigation.prune` alone doesn't remove the O(n²) cost. It does, so those two
were assessed on the mechanism rather than benchmarked full-corpus:

* **Per-directory section-index pages** — changes nav *shape*, not per-page nav
  *size*; without prune, Material still renders the whole tree on every page, so
  this is not a performance lever on its own. `build.py` already emits each
  directory's `index.md` as its section's first entry.
* **Splitting the build** (one MkDocs site per top-level category, stitched) —
  would also remove the O(n²), but at real cost: cross-section nav and MkDocs's
  cross-section link validation are lost, and it needs a bespoke stitching layer
  and synthetic top index. Only worth it if prune were insufficient; it isn't.

**Decision.** Enable `navigation.prune` in `mkdocs.yml` (`theme.features`). One
line, no new dependency. The `mkdocs build` render — the "build" the target
names — is ~9 min (single-digit, target met); `sndocs build` end-to-end is
~11 min once Pagefind's ~2 min is added, still comfortably inside the ~19 min
subtree extrapolation that was the pessimistic bound. The auto-generated nav is
unchanged (`build_nav()` is untouched); spot-checking pruned deep pages from the
full build (e.g. `api-reference/GlideFormAPINX/index.html`) confirms each page
still renders its mirrored ancestor + sibling structure and `index.md` section
landing pages still work (user stories 18, 19). `tests/cli/test_build_cli.py`
pins the feature; the existing Seam B build/nav tests now exercise it.

How the numbers were produced (corpus and harness aren't committed — repo is
code/config only): drive `mkdocs.commands.build.build` directly on
`.sndocs/normalized/`, passing `nav=sndocs.build.build_nav(...)` and
`load_config(..., docs_dir=..., theme={... "features": [...]})`, timing the
`build()` call; Pagefind timed separately as `python -m pagefind --site`.

**HTML minification** (the "minify to the fullest extent" ask alongside #25) was
measured here and deferred; it is now adopted as a parallel `minify-html`
post-build pass, on by default — see `docs/adr/0002-html-minification.md`
(issues #31–#34). Markdown output is untouched — the normalizer's formatting
guarantees stand.
