# ADR-0010: Bound build workspaces and distinguish smoke output

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decision owner:** Victor Bilgin
- **Related commit:** `3198cfa` — `Optimize build storage and add smoke mode`

## Context

A complete build renders tens of thousands of pages per release family. The original pipeline retained each family's source snapshot, transformed Markdown, generated site, and copied output until the entire build ended. MkDocs Material also rendered the complete navigation hierarchy into every page. A stopped local build reached 41 GB of temporary storage, while the single-threaded Python rendering process kept one logical CPU core busy. System-managed temporary paths made this growth difficult to inspect, and the only lightweight test path required editing persistent configuration.

## Decision

Create automatic workspaces below the repository's ignored `.temp/` directory and remove each family workspace as soon as its output is complete. Preserve an explicitly supplied `--work-dir` for diagnostics. Render MkDocs directly into the assembled family output, and reuse unchanged or archived family trees with hard links when the filesystem permits, falling back to ordinary copies.

Enable Material's pruned navigation so inactive branches are not repeated in every generated page. Keep production search and complete-family behavior unchanged. Provide a distinct `--smoke` build profile that selects only the newest family, disables search indexing, retains strict validation, records its profile in the manifest, and cannot be packaged as a production artifact. Production and smoke outputs are not incrementally interchangeable.

Stream local `git archive` output into extraction rather than buffering the complete archive in memory. Report build phases, elapsed time, sizes, reuse method, and workspace cleanup instead of throttling the CPU; sustained use of one logical core remains acceptable when it represents useful rendering work.

## Consequences

- Temporary storage is bounded by one family's source and transformed Markdown instead of accumulating complete family sites.
- Pruned navigation reduces repeated HTML, rendering work, final artifact size, and browser DOM size while retaining access to the configured hierarchy.
- Developers can run a representative strict smoke build quickly, but smoke output intentionally does not test production search or multi-family assembly.
- Explicit diagnostic workspaces remain the developer's responsibility to remove.
- Hard-link reuse saves storage only when source and destination share a filesystem; behavior remains portable through the copy fallback.

## Alternatives considered

- **Keep macOS system temporary storage:** Rejected because repository-local ignored workspaces are easier to discover, measure, and clean deliberately.
- **Throttle the Python process:** Rejected because it would extend builds without eliminating redundant rendering work.
- **Disable search in all builds:** Rejected because production search is part of the accepted site experience.
- **Retain generated family sites in the workspace:** Rejected because the assembled output already provides the durable copy.
