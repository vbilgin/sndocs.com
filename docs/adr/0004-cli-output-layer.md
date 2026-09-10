# ADR 0004 — `rich` for the shared CLI output layer

Status: accepted (issue #46, parent #45; v1.2)
Date: 2026-09-09

## Context

Every `sndocs` command does minutes of work and prints nothing until it
finishes (parent #45). v1.2 gives the CLI a consistent progress and diagnostics
experience: a live bar for the countable work (`normalize`, `build`'s minify
pass), a spinner with elapsed time for the opaque work (`fetch`, the MkDocs
render, Pagefind indexing), styled warning/error blocks, `-v/-q/--color`
verbosity flags, and graceful degradation when stderr is not a terminal (CI,
pipes) — no redrawing bar, no ANSI, plain periodic progress lines.

The parent spec already fixes the shape of the solution: one output abstraction
(working name **Reporter**) that every command shares, so behaviour is decided
in one place rather than sprinkled through five commands (user story 31), and
that abstraction is unit-testable without a real terminal (user story 32).

What this ADR settles is the library that abstraction wraps. The needs, taken
together:

- determinate progress bars with bar + absolute `done/total` + percentage +
  elapsed + estimated-time-remaining columns, driven by real per-item
  completion;
- indeterminate spinners with an elapsed timer;
- non-terminal detection, so the same code path emits plain lines into a
  captured log instead of control characters;
- `NO_COLOR` support and an `auto|always|never` colour override
  (user stories 26, 27);
- styled, readable warning and error blocks;
- formatted tracebacks at `-vv` for bug reports (user story 19);
- all of the above writing to **stderr**, with the retained one-line summaries
  still on **stdout** (user story 28).

## Decision

Add **`rich` (`>=13`)** as a runtime dependency of the `sndocs` package, and
build the Reporter abstraction on top of it in a single new module,
`src/sndocs/reporter.py`. **Nothing else in the codebase imports `rich`
directly** — the module is the only seam, mirroring how `sndocs.minify` is the
only importer of `minify-html` (ADR 0002). A unit test enforces this.

`rich` covers every item on the list above in one dependency: `rich.progress`
gives the bar with exactly the columns wanted (`BarColumn`,
`MofNCompleteColumn`, `TaskProgressColumn`, `TimeElapsedColumn`,
`TimeRemainingColumn`) and the spinner (`SpinnerColumn` + `TimeElapsedColumn`);
`rich.console.Console` does TTY detection, honours `NO_COLOR`, and takes an
explicit `file=` / `force_terminal=` so the Reporter constructor can be handed a
`Console` backed by a `StringIO` for tests; `rich.panel.Panel` gives the styled
warning/error blocks; `rich.traceback` gives the `-vv` formatted traceback. It
is pure Python and widely used. It is not currently in the dependency tree, but
its own requirements are nearly free here: `markdown-it-py` is already a direct
dependency (ADR 0001), leaving only `pygments` as genuinely new.

`>=13` is the floor: the `MofNCompleteColumn` / `TaskProgressColumn` split and
the `Console(no_color=...)` argument used by the Reporter's tests have been
stable since rich 13.0 (2022). No upper pin — the Reporter locks the specific
behaviour it depends on with its own tests, the same way `sndocs.minify` pins
every `minify-html` keyword.

## Rejected alternatives

- **`tqdm`.** The de-facto progress-bar library, but *only* a progress bar. It
  has no spinner-with-timer, no styled error/warning blocks, no
  formatted-traceback rendering, and no colour/`NO_COLOR` policy — each of those
  would still be hand-rolled. `tqdm` also detects a non-TTY only to the extent
  of disabling its own animation; the "emit a plain periodic progress line into
  the log instead" behaviour (user story 24) is still on us. Adopting `tqdm`
  would mean `tqdm` **plus** a second, home-grown layer for everything else —
  more surface than one `rich` dependency, split across two idioms.

- **A hand-rolled solution** (`sys.stderr.isatty()`, manual `\r` redraws, ANSI
  escapes gated on a `--color` flag, a bespoke ETA calculation, a
  `traceback.format_exception` wrapper). This is the option that looks cheap and
  is not. The edge cases are the whole job: correct TTY vs pipe vs redirect vs
  CI detection, `NO_COLOR` **and** `--color=always` interacting, width probing
  and reflow, not corrupting a live bar when a warning is printed mid-run
  (user story 13), carriage-return cleanup on exceptions, Windows terminals.
  `rich` has solved these; re-deriving them by hand is exactly the "TTY/colour/CI
  edge cases" trap this ADR exists to avoid, and it would still need the same
  test seam.

## Consequences

- One new runtime dependency (`rich>=13`), pure-Python, no build step, no
  network at runtime — `sndocs` stays offline.
- `src/sndocs/reporter.py` is the sole importer of `rich`; every command will
  receive a `Reporter` rather than touching `rich` or writing to a stream
  directly. `test_only_reporter_imports_rich` fails if another module imports
  `rich`.
- The Reporter constructor takes an injected `rich.Console`, so its rendering
  and verbosity rules are covered by fast unit tests that build a `Console` over
  a `StringIO` with `force_terminal` set either way — no pseudo-terminal, no
  snapshot of control characters (assertions are on text like `5/5`, `100%`,
  `WARNING:`, `ERROR:`, not on glyphs or frame counts).
- This ticket (#46) ships the dependency, this ADR, and the fully-tested
  `Reporter` module only. **No command imports it yet**
  (`test_cli_does_not_import_reporter_yet` enforces that); the per-command
  wiring lands in the follow-up tickets under #45.

## Follow-ups

- The `-v/-q/--color` global flags on the `cli()` group, and constructing the
  `Reporter` from them onto the Click context — next ticket under #45.
- Per-command adoption (`fetch` spinner, `normalize` bar + repair summary,
  `build` phase spinners + minify bar, `serve` error path, `all` step labels
  and timing breakdown) — the remaining #45 children.
</invoke>
