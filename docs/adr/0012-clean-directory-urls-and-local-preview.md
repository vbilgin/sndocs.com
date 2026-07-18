# ADR-0012: Preserve clean directory URLs and provide local HTTP preview

- **Status:** Accepted
- **Date:** 2026-07-18
- **Decision owner:** Victor Bilgin
- **Related commit:** `683e6fd` — `Add clean URL preview server`

## Context

MkDocs emits each topic as a directory containing `index.html` and links to it with a trailing slash. Static web servers resolve that layout to a clean URL, but opening the generated tree through `file://` navigates to the directory rather than loading its index document. Emitting explicit `index.html` links would make filesystem browsing work at the cost of exposing filenames in public URLs. Slashless extension-free URLs would require provider-specific rewrites and weaken the host-agnostic artifact contract.

## Decision

Keep MkDocs directory URLs explicitly enabled. The supported public topic form is `/family/path/topic/`, backed by `family/path/topic/index.html` in the artifact.

Add `sndocs serve` as the supported local-preview workflow. It serves an existing generated tree with Python's standard-library HTTP server, binds to `127.0.0.1:8000` by default, accepts site, bind-address, and port overrides, and does not open a browser automatically. Direct `file://` browsing is not supported.

## Consequences

- Navigation behaves consistently in local HTTP previews and on ordinary static hosts.
- Public topic URLs remain clean and the packaged tree remains host-agnostic.
- Contributors must run the preview command instead of opening generated HTML directly from disk.
- The public CLI gains a long-running command but no new runtime dependency.

## Alternatives considered

- **Link directly to `index.html`:** Rejected because it exposes implementation filenames in public URLs.
- **Emit sibling `.html` files:** Rejected because it abandons the established clean directory layout.
- **Require slashless extension-free URLs:** Rejected because they need hosting-provider redirects or rewrites.
- **Only document `python -m http.server`:** Rejected in favor of one discoverable project command with stable defaults.
