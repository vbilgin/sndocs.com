# ADR-0013: Simplify and harden the public CLI

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** Victor Bilgin
- **Related commit:** `Pending`

## Context

The initial CLI mixed reusable-source lifecycle operations into discovery and builds, silently replaced existing output directories, named incremental input by chronology rather than purpose, and exposed GitHub Actions plumbing as a general build option. Build progress and manifests also shared standard output, which made automation fragile. Contributors need a safer interactive contract and deterministic machine-readable results without weakening reproducible source snapshots, incremental family reuse, archived-family retention, or named build profiles.

## Decision

Supersede the public option names in ADR-0008 while retaining its clean, offline, exact-commit snapshot invariants. Release a breaking `0.2.0` CLI. Manage reusable clones with `source clone`, `source update`, and offline `source check`; discovery and builds accept an existing clone through `--source`. Existing build output is rejected unless `--clean` explicitly authorizes replacement, and source discovery and validation occur before deletion. Rename incremental input to `--reuse-from` and require it to differ from output.

Allow repeatable per-run `--family` selection to override configuration while preserving upstream ordering. Smoke remains a named, non-packageable profile, defaults to the newest family, and may target one explicit family. A side-effect-free build planner determines rebuild, reuse, and archive actions for both `--dry-run` and execution.

Finite commands provide concise human summaries or exactly one JSON result on standard output, with progress and diagnostics on standard error. GitHub Actions outputs are written automatically only after successful real builds when `GITHUB_OUTPUT` is present. Removed options receive no compatibility aliases.

## Consequences

- Destructive output replacement requires explicit authorization and cannot precede source validation.
- Source clone creation, network refresh, and offline verification are independently discoverable operations.
- Dry-run decisions and actual incremental execution share one policy implementation.
- Automation has a portable JSON interface while the workflow retains native GitHub output integration.
- Existing scripts must adopt the breaking option and command names.

## Alternatives considered

- **Retain flat source flags:** Rejected because cloning, updating, and selecting a source have distinct lifecycles and network effects.
- **Prompt before replacement:** Rejected because prompts complicate unattended builds and do not provide a stable safety contract.
- **Build incrementally in place:** Deferred because safe atomic replacement requires a broader storage and failure-recovery design.
- **Keep permanent aliases:** Rejected in favor of a small, unambiguous public interface at the intentional version boundary.

## Related decisions

- [ADR-0008](0008-reproducible-local-source-snapshots.md) defines clean local snapshot behavior.
- [ADR-0010](0010-bound-build-workspaces-and-smoke-profile.md) defines workspace cleanup and smoke-profile invariants.
