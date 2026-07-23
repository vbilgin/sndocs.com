# ADR-0008: Use reproducible local source snapshots for testing

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decision owner:** Victor Bilgin
- **Related commit:** `49f4ae1` — `Add reusable local upstream source support`
- **Superseded in part by:** [ADR-0013](0013-simplify-and-harden-cli.md) for public CLI names; snapshot invariants remain accepted

## Context

The pipeline normally performs network discovery and a shallow clone for every family it builds. Complete families contain tens of thousands of files, so repeatedly transferring them makes local integration testing unnecessarily slow. A reusable clone can remove that transfer cost, but reading its working tree or switching branches would make results depend on user state and could modify the clone during a build.

## Decision

Provide `--source-repo` and `--clone-source` on `discover` and `build`. Keep these machine-specific paths out of project configuration. A standard full clone retains all family branches as remote-tracking refs, and an existing destination is never overwritten.

Require a local source working tree to be clean, including untracked files, and require exactly one SSH or HTTPS remote matching the configured GitHub repository. Read `llms.txt` from that remote's symbolic default-branch ref and resolve family SHAs from its remote-tracking refs.

Local operation is offline by default. Fetch and prune the matching remote only when `--refresh-source` is explicitly supplied with `--source-repo`. Materialize exact family commits into isolated build workspaces with `git archive`; do not switch branches, consume working-tree edits, or modify the source clone.

Complete source preparation, validation, discovery, and ref resolution before deleting existing build output or invoking MkDocs. Preserve commit SHA manifest semantics so remote and local builds remain compatible for incremental reuse.

## Consequences

- Repeated local builds avoid upstream discovery requests and per-family network clones.
- Local results are reproducible from committed refs and do not depend on the checked-out branch.
- Developers must explicitly refresh stale refs and cannot use uncommitted upstream edits for pipeline testing.
- Clones with missing default-branch metadata, missing family refs, mismatched remotes, or dirty working trees fail before build output changes.

## Alternatives considered

- **Build the current working tree:** Rejected because only one family can be checked out and uncommitted state has no stable manifest identity.
- **Switch the reusable clone between families:** Rejected because builds would mutate user state and concurrent family work would be unsafe.
- **Fetch on every local run:** Rejected because it restores network latency and removes deterministic offline snapshot behavior.
- **Store local paths in `pipeline.toml`:** Rejected because machine-specific paths are easy to commit accidentally and are not production configuration.
