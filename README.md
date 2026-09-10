# sndocs.com

A Python CLI (`sndocs`) that turns the
[ServiceNow/ServiceNowDocs](https://github.com/ServiceNow/ServiceNowDocs)
Markdown corpus into a locally-served static docs site, built with MkDocs and
Material for MkDocs.

This repository holds code and config only. It does not house releases, CI/CD
automation, or generated output. v1 targets the `australia` release branch.

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
| `sndocs fetch`    | Shallow-clone (or update) the `australia` branch into `.sndocs/repo/`.  |
| `sndocs normalize`| Normalize `.sndocs/repo/` into `.sndocs/normalized/`.                   |
| `sndocs build`    | Render the MkDocs site into `.sndocs/site/` and index it with Pagefind. |
| `sndocs serve`    | Serve `.sndocs/site/` on localhost — no rebuild, no watch.             |
| `sndocs all`      | `fetch` → `normalize` → `build` in sequence.                            |

`sndocs --version` reports the installed version. `sndocs COMMAND --help` shows
per-command options (`--workers`, `--minify/--no-minify`, `--port`, …).

Everything generated lives under the project-local, gitignored `.sndocs/`
directory: `repo/` (cloned source), `normalized/` (normalized Markdown), and
`site/` (built site). Only `fetch` needs network access.

## Development

```sh
pytest
```

Design decisions are recorded in `docs/adr/`. See `CLAUDE.md` for repository
conventions and `docs/agents/` for agent-facing guides.
