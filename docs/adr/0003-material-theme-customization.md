# ADR 0003 — Material theme customization without an asset pipeline or multi-version toolchain

Status: accepted (issue #42, v1.1)
Date: 2026-09-09

## Context

v1.1 gives the built site its own identity: the lowercase **sndocs** wordmark,
a five-colour palette (Classic Crimson, Majorelle Blue, Pumpkin Spice, Carbon
Black, Parchment) in paired light/dark schemes, a header repo link, ServiceNow
attribution in the footer, and a "Release family: Australia" affordance in the
header.

Two structural constraints shape how this is delivered:

1. **There is no place to put a stylesheet.** Material's documented way to add
   CSS is `extra_css:` pointing at a file under `docs_dir`. Here `docs_dir` is
   `.sndocs/normalized/` — the generated, `.gitignore`d output of `sndocs
   normalize`, rewritten from scratch on every run. A committed `.css` file
   cannot live there, and `sndocs build` deliberately does not copy anything
   into it (ADR 0001; the repo is "code/config only", CLAUDE.md). There is no
   build step that compiles or bundles front-end assets, and adding one is out
   of proportion to a few dozen lines of CSS.

2. **"Release family" is not "version".** Material ships a version selector
   (`mike` + `extra.version`) for projects that publish many doc versions side
   by side. sndocs v1 publishes exactly one release family (Australia, issue
   #5 / CLAUDE.md), from one upstream branch. Wiring up `mike`, a versioned
   `site_dir` layout, and a `versions.json` to render a dropdown with one entry
   would be pure ceremony.

## Decision

### a. Palette + identity CSS: an inline `<style>` block in `overrides/main.html`

The five-colour palette, the wordmark styling, and the release-selector styling
are one `<style>` block appended to `{% block styles %}` in
`overrides/main.html` — after Material's `main.css` and `palette.css` `<link>`s,
so equal-specificity overrides win. `overrides/` is `custom_dir`, already
committed, already the seam this project uses for theme changes (the Pagefind
search widget lives there too).

The block defines the raw palette once, then a light role mapping under
`[data-md-color-scheme="default"]` and a dark one under
`[data-md-color-scheme="slate"]`, and finally maps those roles onto Material's
own custom properties (`--md-primary-fg-color`, `--md-accent-fg-color`,
`--md-default-bg-color`, …). `mkdocs.yml`'s `theme.palette` keeps the two
schemes, the `prefers-color-scheme` media default, and the manual toggle;
the `<style>` block only recolours them.

One asymmetry is handled explicitly: `--md-primary-fg-color` drives both the
header bar *and* every other primary affordance. In light both are Crimson, so
the variable suffices. In dark the affordances stay lightened Crimson
(`#f2536a`) but the header bar is Carbon — so `--md-primary-fg-color` is set to
the affordance colour and a single `.md-header { background-color: … }` rule
per scheme pins the bar.

### b. Release-family selector: a static, CSS-only `<details>` — not `mike`

The header carries a `<details class="sndocs-release">` disclosure: the
`<summary>` shows a small "Release family" caption, a prominent "Australia", and
a chevron; opening it reveals a one-row menu listing "Australia", marked
current. No JavaScript, no navigation, no `mike`, no `extra.version`. It is an
honest statement of scope ("this site is the Australia release family"), with
room to become a real switcher if sndocs ever publishes a second family.

Its markup is a small addition to a local copy of `partials/header.html` in
`overrides/partials/` — placed directly after the wordmark span, inside the
flex `.md-header__topic`, so it flows beside the wordmark with no hardcoded
offset and inherits Material's own fade/slide when the header title switches to
the page heading on scroll. Its styling is in the `main.html` `<style>` block
with the rest of the identity CSS.

The same `header.html` copy also wraps the site name in
`<a class="sndocs-wordmark">`: stock Material's only header home link is the
logo `<a>`, and the identity CSS hides the logo (no image, no
`theme.icon.logo`), so without this the header would have no way back to the
site root. Both edits are tagged `sndocs:` in the file and are the *only*
divergence from the stock template;
`test_vendored_header_tracks_installed_material` fails if the copy ever drops an
upstream line, so a Material upgrade that restructures the partial is caught
rather than silently shadowed.

### c. `overrides/partials/copyright.html` for footer attribution

Material renders `partials/copyright.html` in the footer on every page. A local
copy replaces the single plain-text `config.copyright` line with the full
linked attribution (ServiceNow copyright, the `ServiceNow/ServiceNowDocs`
source, the Apache-2.0 licence) plus the independence / trademark notice,
keeping "Made with Material for MkDocs". The plain-text `copyright:` in
`mkdocs.yml` stays as a fallback.

### d. Binary assets (favicon, logo image) remain deferred

A favicon and a logo image are `docs_dir`-blocked the same way a `.css` file is
— MkDocs resolves `theme.favicon` / `theme.logo` relative to `docs_dir`, which
is generated. Solving that needs `sndocs build` to copy committed static assets
into the render, or Material's `custom_dir` static-file handling to be wired up
and tested. That is its own ticket; v1.1 ships the text wordmark only (no
image, no `theme.icon.logo`) and no favicon.

## Rejected alternatives

- **`extra_css:` with a file under `docs_dir`.** The file would be clobbered on
  every `sndocs normalize`, or would require `sndocs build` to inject it into
  the generated tree — new moving parts for a small amount of CSS. Revisit only
  if the identity CSS grows enough to warrant its own build step (which would
  also unblock binary assets — item d).
- **A front-end asset pipeline** (npm, a bundler, Material's own build from
  source). Far out of proportion; the project is a Python CLI with no
  JavaScript build.
- **`mike` / Material's version machinery for the release-family selector.**
  Built for many concurrent doc versions; sndocs has one. All cost, no benefit
  until a second release family is in scope.
- **A separate `overrides/` stylesheet loaded via `{% block styles %}`
  `<link>`.** Material serves `custom_dir` files, so this can work, but it
  splits the identity CSS across two files for no gain over an inline block of
  this size. If the CSS grows, promote it to a file then.
- **Editing `partials/header.html` more heavily** (restructuring the header).
  The local copy keeps every stock line, adding only the `<details>` block and
  the wordmark home-link `<a>`, to keep the diff against a future Material
  release trivial to re-apply — and a test enforces that.

## Consequences

- Recolouring is a single reviewable block in `overrides/main.html`; changing a
  palette role is a one-line edit there.
- `overrides/partials/header.html` and `overrides/partials/copyright.html` are
  now version-pinned copies of Material internals. If Material restructures
  either partial, the copies must be re-synced; both are kept minimal to make
  that cheap, both carry a header comment saying so, and
  `test_vendored_header_tracks_installed_material` fails when `header.html`
  drifts from the installed template.
- No new dependencies, no build step, no network at build time — `sndocs build`
  stays offline and `pytest` covers the config + rendered output.
- Favicon and logo image are explicitly still missing; tracked as a follow-up.

## Follow-ups

- **Binary theme assets (favicon, logo image).** Needs a committed-static-asset
  path into the MkDocs render; would also let the identity CSS move to a real
  file. Its own ticket.
- **Re-sync the `overrides/partials/` copies** on any Material upgrade that
  touches `header.html` or `copyright.html`.
