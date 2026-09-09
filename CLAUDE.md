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

## Branching and PRs

- **One branch per issue.** When implementing a GitHub issue that is an
  actual ticket (has concrete acceptance criteria to build against), do the
  work on its own branch, not directly on `main`.
- **Spec/parent issues are exempt.** An issue that only groups sub-issues
  (e.g. a "vN spec" parent with its own checklist of child tickets, no
  standalone acceptance criteria) doesn't get a branch or PR of its own —
  only its child tickets do.
- **Push means PR.** Once a branch's work is pushed, open a PR for it as a
  **draft** — don't leave pushed work without a PR. Never merge it yourself;
  the user reviews and merges.
- Non-ticket work (e.g. a direct doc-edit request like this one) still gets
  its own small branch/PR rather than landing on `main` directly, unless the
  user says otherwise.

## Worktrees

- **Always work in a worktree for code/config changes.** Call the
  `EnterWorktree` tool before the first edit — every session, no exceptions,
  whether or not the harness prompts for it. Consistency matters more than
  the marginal case where isolation seems unnecessary.
- **Doc-only edits are the sole carve-out.** Prose, ADRs, README, and this
  file may land on `main` directly (see
  [Branching and PRs](#branching-and-prs)) and don't need a worktree —
  except when a harness guard blocks editing the shared checkout (e.g.
  background sessions), in which case use a worktree for those too.
- Commit — and push, if there's a remote — from the worktree before
  finishing, so the work survives the worktree being cleaned up.

## Merging PRs

- **You may merge PRs, but only with the user's explicit go-ahead for that
  specific PR.** Never merge unprompted. Approval of one PR does not carry
  over to the next — ask again each time.
- Still never force-push, and never push directly to `main`/`master` outside
  the normal PR merge.

## Agent skills

### Issue tracker

Issues live as GitHub Issues in `vbilgin/sndocs.com`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
