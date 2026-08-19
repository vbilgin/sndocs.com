# CLAUDE.md

Guidance for working in this repository.

## What this project is

A Python CLI (`sndocs`) that fetches the ServiceNowDocs Markdown corpus,
normalizes it, and builds a static docs site with MkDocs + Material for
MkDocs, served locally. Nothing is implemented yet — see the issue tracker
for the v1 spec before building anything.

## Ground rules

- **This repo is code/config only.** Never commit generated artifacts:
  cloned source, normalized Markdown, or built site output.
- **No GitHub Actions / CI automation.** This repo intentionally has none —
  don't add workflow files.
- **No release/hosting concerns here.** Deploying to sndocs.com is explicitly
  out of scope for v1. Don't add deployment tooling unless asked.
- **v1 targets the `australia` branch only.** Don't add multi-version
  support unless explicitly requested.

## Agent skills

### Issue tracker

Issues live as GitHub Issues in `vbilgin/sndocs.com`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
