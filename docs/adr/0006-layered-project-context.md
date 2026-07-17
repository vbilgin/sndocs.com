# ADR-0006: Maintain layered repository context for agents and contributors

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owner:** Victor Bilgin

## Context

Conversation histories and agent context windows are finite, while this project will continue across multiple sessions and potentially multiple human and agent contributors. An append-only worklog alone eventually becomes too large to load routinely, and Git history alone does not efficiently communicate current architecture, invariants, known risks, or next work.

The repository needs durable context that is concise enough for routine agent orientation while preserving searchable history and decision rationale.

## Decision

Use four complementary layers:

- Root `AGENTS.md` provides short repository-wide operating instructions and tells agents which context to read and maintain.
- `.agent/CONTEXT.md` is the bounded primary handoff document containing current objective, architecture, invariants, status, risks, next work, and verification commands.
- `.agent/WORKLOG.md` is a reverse-chronological record of significant outcomes, decisions, verification, and follow-up work; agents consult it selectively and archive older entries when it grows large.
- `docs/adr/` contains durable architectural decisions and their rationale.

Use Git history as the authoritative record of exact changes, commit authorship, and diffs. Update context and worklog documentation before committing when possible, include those updates with the implementation commit, and do not create follow-up commits solely to insert a commit SHA.

Do not store prompts, full conversation transcripts, hidden reasoning, secrets, or reproduced diffs in the context system. Agents must still inspect the actual repository because documentation can become stale.

## Consequences

- New contributors can obtain current context without loading the entire project history.
- Historical work and durable rationale remain available through targeted lookup.
- The same information may appear at different levels of abstraction, requiring disciplined maintenance to prevent contradictions.
- `CONTEXT.md` must be actively condensed rather than allowed to grow as an append-only log.
- Non-agent commits are incorporated when the next agent reconciles significant unlogged Git history.

## Alternatives considered

- **Use only `WORKLOG.md`:** Rejected because an ever-growing log recreates the context-limit problem.
- **Use only Git history:** Rejected because commit subjects and diffs do not provide a compact current-state handoff.
- **Put all information in `AGENTS.md`:** Rejected because repository instructions should remain short and stable.
- **Automatically create bot commits after every push:** Rejected because it creates commit noise, recursion concerns, and avoidable merge conflicts.
