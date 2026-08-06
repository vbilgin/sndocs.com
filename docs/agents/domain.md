# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo already has its own layered context system, formalized in [ADR-0006](/docs/adr/0006-layered-project-context.md). It plays the role the generic `CONTEXT.md` / `docs/adr/` convention plays elsewhere — read these instead of expecting a root `CONTEXT.md`.

## Before exploring, read these

- **[AGENTS.md](/AGENTS.md)** — short, stable repository instructions. Read first, every time.
- **[.agent/CONTEXT.md](/.agent/CONTEXT.md)** — bounded current-state handoff (architecture, invariants, interfaces, status, risks, next steps). Read it in full before substantial work.
- **[.agent/WORKLOG.md](/.agent/WORKLOG.md)** — reverse-chronological significant work. Search it selectively (grep for a topic/date), never load it wholesale. Older entries archive to `.agent/worklog/YYYY-HN.md`.
- **[docs/adr/](/docs/adr/README.md)** — accepted ADRs, current policy. Read only the ones relevant to the area you're about to work in.

This is a single-context repo — there is one `AGENTS.md` / `.agent/CONTEXT.md` / `docs/adr/` set at the root, not a `CONTEXT-MAP.md` with per-context docs.

## Repository state is authoritative over documentation

If what you read in code conflicts with `.agent/CONTEXT.md` or an ADR, report the conflict rather than silently picking one — this is an explicit rule in `CLAUDE.md`.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `.agent/CONTEXT.md` or the relevant ADR. Don't drift to synonyms the docs explicitly avoid.

If the concept you need isn't documented yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap worth noting.

## Flag ADR conflicts

Never rewrite accepted ADR rationale. If your output contradicts an existing ADR, surface it explicitly and propose a new numbered ADR to supersede it, rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
