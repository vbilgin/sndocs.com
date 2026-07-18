# Repository Agent Instructions

These instructions apply to the entire repository. Keep this file short and stable; project state belongs in `.agent/CONTEXT.md`, historical work in `.agent/WORKLOG.md`, and durable decisions in `docs/adr/`.

## Load context before substantial work

1. Read all of `.agent/CONTEXT.md`.
2. Inspect Git status, recent commits, and the source, configuration, and tests relevant to the task. Repository state is authoritative.
3. Search `.agent/WORKLOG.md` and archived worklogs selectively for relevant components, errors, decisions, or commit subjects. Do not load complete worklogs by default.
4. Read only the ADRs relevant to the task. Accepted ADRs are current policy unless a later ADR explicitly supersedes them.
5. Report conflicts among code, tests, configuration, context, and ADRs rather than silently choosing one.

## Repository rules

- Use the public `ServiceNow/ServiceNowDocs` repository and its `llms.txt` as the documentation source. Do not scrape `servicenow.com/docs`.
- Follow accepted ADRs, including strict MkDocs validation, archived-family retention, deterministic transformations, source attribution, Apache-2.0 notices, and the independent-site disclaimer.
- Preserve upstream meaning. Recover malformed source data only when the result is deterministic and auditable.
- Do not commit generated Markdown, HTML, build directories, downloaded upstream repositories, packaged artifacts, caches, or virtual environments.
- Avoid complete family builds unless the task requires integration validation; they are network-, disk-, and time-intensive.
- Preserve unrelated user changes and work safely in a dirty worktree.

## Branding resources

- Before creating or modifying branded site, README, repository, or promotional materials, consult `local/branding/` as the authoritative local branding reference.
- Use `local/branding/brand_colors.json` for machine-readable color definitions and `local/branding/color_palette.png` for a visual reference. The current palette is Classic Crimson `#d7263d`, Majorelle Blue `#6a4cff`, Pumpkin Spice `#ff8c42`, Carbon Black `#262626`, and Parchment `#faf7f2`; read the source files for exact current values.
- Use the light- or dark-background SVG logomark from `local/branding/design_files/exports/` as appropriate. Preserve supplied assets rather than recreating or approximating them; editable source artwork is in `local/branding/design_files/logo.ai`.
- `local/` is intentionally Git-ignored. Reference its contents locally, but do not add them to Git or assume they are available in clones or automated environments.

## Development and verification

- Support Python 3.11 or newer and use the existing virtual-environment workflow documented in `README.md`.
- Prefer existing dependencies. New dependencies require justification, `pyproject.toml` changes, and a synchronized `requirements.lock`.
- Add or update tests for behavioral changes, especially parsing, navigation, link resolution, incremental reuse, manifests, and packaging.
- Run `.venv/bin/pytest` for Python changes.
- Run strict fixture or build validation when generation behavior changes.
- For documentation-only changes, verify referenced paths and links, inspect Markdown structure, and run `git diff --check`.
- Treat a complete multi-family build as targeted integration validation, not a routine pre-commit check.
- Report verification that was performed, skipped checks, failures, and remaining risks.

## Maintain project context

- Update `.agent/CONTEXT.md` only when material work changes architecture, invariants, interfaces, current status, known risks, or next steps.
- Keep `CONTEXT.md` below both 150 lines and 1,000 words. Replace stale information instead of appending history.
- Add reverse-chronological `.agent/WORKLOG.md` entries for significant implementation, diagnosis, decisions, or operational milestones. Do not log minor edits or routine questions.
- Keep each prose paragraph and list item on one Markdown source line.
- Worklog entries should record outcome, contributor, committer when known, commit subject or SHA when available, decisions, verification, and follow-up.
- Reconcile significant unlogged commits at the beginning of later agent work regardless of author or committer.
- Archive older entries when the active worklog exceeds 20 entries or 400 lines, whichever comes first. Move them to `.agent/worklog/YYYY-HN.md` and link the archive from the active log.
- Never store prompts, full conversation transcripts, hidden reasoning, secrets, or reproduced diffs in repository context files.

## Maintain architecture decisions

- Create a new numbered ADR for durable decisions affecting architecture, interfaces, lifecycle, deployment, or contributor workflow.
- Name ADRs `NNNN-kebab-case.md`, add them to `docs/adr/README.md`, and include status, date, owner, context, decision, consequences, alternatives, and related commits when available.
- Do not rewrite accepted rationale when policy changes. Create a superseding ADR and cross-link both records.

## Git and handoff policy

- Commit only when the user explicitly requests it.
- Before an authorized commit, update context, worklog, and ADR files when material changes require it, and include those updates in the implementation commit.
- Refer to an uncreated commit by its intended subject or as `Pending`. Do not create a follow-up commit solely to insert its SHA.
- Never include unrelated user changes in an agent commit without authorization.
- End work with a concise summary of changes, verification performed, skipped checks, and remaining risks.
