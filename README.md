# sndocs.com

A Python CLI (`sndocs`) that turns the
[ServiceNow/ServiceNowDocs](https://github.com/ServiceNow/ServiceNowDocs)
Markdown corpus into a locally-served static docs site, built with MkDocs and
Material for MkDocs. The upstream corpus is used **unmodified** except for
mechanical, render-preserving normalization (fence and table repair, redundant
escape removal, link rewriting) — no editorial change, nothing added or
removed. The built site presents as **sndocs**, an independent, unendorsed
mirror; see [Attribution and licensing](#attribution-and-licensing).

This repository holds code and config only. It does not house releases, CI/CD
automation, or generated output. `sndocs fetch` defaults to the `australia`
release family; pass `--release` (or set `SNDOCS_RELEASE`) to fetch a
different one — see [Usage](#usage). `normalize`/`build`/`all` do not yet have
their own release selection and continue to assume a single fetched release.

## Install

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

This puts a `sndocs` console command on your PATH.

## Usage

Run the whole pipeline from a clean checkout, then serve it:

```sh
sndocs all      # fetch -> normalize -> build
sndocs serve    # static server over the last build, on localhost
```

Or run the steps individually:

| Command           | What it does                                                             |
| ----------------- | ----------------------------------------------------------------------- |
| `sndocs fetch`    | Shallow-clone (or update) a release family's branch into `.sndocs/repo/<release>/` (default `australia`; `--release`/`SNDOCS_RELEASE` select `xanadu`, `yokohama`, `zurich`, `australia`, or `brazil`). |
| `sndocs normalize`| Normalize `.sndocs/repo/` into `.sndocs/normalized/`.                   |
| `sndocs build`    | Render the MkDocs site into `.sndocs/site/` and index it with Pagefind. |
| `sndocs serve`    | Serve `.sndocs/site/` on localhost — no rebuild, no watch.             |
| `sndocs all`      | `fetch` → `normalize` → `build` in sequence.                            |

`sndocs --version` reports the installed version. `sndocs COMMAND --help` shows
per-command options (`--release`, `--workers`, `--minify/--no-minify`,
`--port`, …).

### Progress and output

Long steps report as they go: a progress bar with counts, percentage, elapsed
time and ETA for `normalize` and the `build` minify pass, an elapsed-time
spinner for `fetch` and `build`'s other phases, and per-step labels plus a
timing breakdown for `all`. `normalize` prints a summary of what it
auto-repaired once its bar finishes.

Global flags, accepted before or after the subcommand:

| Flag | What it does |
| ---- | ------------ |
| `-v/--verbose` | Per-item log lines instead of a live bar, plus the underlying `git`, MkDocs, and Pagefind output. Repeat (`-vv`) for debug detail and a formatted traceback on failure. |
| `-q/--quiet` | Errors only — no bars, spinners, summaries, or warnings. A failing run still exits non-zero. |
| `--color=auto\|always\|never` | Colour output; `auto` (the default) honours `NO_COLOR` and a non-terminal stderr. |

`-v` and `-q` together is a usage error. Progress, warnings, and diagnostics go
to stderr; the per-command summary lines go to stdout, so redirecting stdout
captures the summary without the animation. When stderr is not a terminal (CI,
pipes), the animated bar is replaced by periodic plain progress lines and
warnings/errors are prefixed `WARNING:` / `ERROR:`.

Everything generated lives under the project-local, gitignored `.sndocs/`
directory: `repo/<release>/` (cloned source, one subdirectory per fetched
release family), `normalized/` (normalized Markdown), and `site/` (built
site). Only `fetch` needs network access.

## Development

```sh
pytest
```

Design decisions are recorded in `docs/adr/`. See `CLAUDE.md` for repository
conventions and `docs/agents/` for agent-facing guides.

## Attribution and licensing

**Documentation content** comes from
[ServiceNow/ServiceNowDocs](https://github.com/ServiceNow/ServiceNowDocs) and is
copyright © ServiceNow, Inc., licensed under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). sndocs
applies only mechanical, render-preserving normalization to that content (fence
and table repair, redundant escape removal, link rewriting); it makes no
editorial change and adds or removes nothing.

sndocs is an **independent project** — not affiliated with, endorsed by, or
sponsored by ServiceNow, Inc. "ServiceNow" and ServiceNow release-family names
(such as "Australia") are trademarks of ServiceNow, Inc., used here only to
identify the documentation being mirrored.

**sndocs' own code** in this repository is licensed under the Apache License 2.0
— see [`LICENSE`](LICENSE). Copyright 2026 Victor Bilgin.

