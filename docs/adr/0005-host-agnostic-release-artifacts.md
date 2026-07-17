# ADR-0005: Publish host-agnostic rolling release artifacts

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decision owner:** Victor Bilgin
- **Related commit:** `dbc74ff` — `feat: add ServiceNowDocs-to-MkDocs build pipeline`

## Context

The initial deployment provider is intentionally unspecified. The output must be usable by any static host, preserve archived family state, avoid committing a very large generated site to the main branch, and support scheduled unattended refreshes.

Ordinary GitHub Actions artifacts have finite retention and therefore cannot serve as the durable archive source for families removed upstream.

## Decision

Assemble a complete host-root directory and package it as `sndocs-site.tar.gz` and `sndocs-site.zip`, with a SHA-256 checksum for each archive. Include version metadata, the build manifest, link report, and ServiceNow license notice inside the static tree.

Use a daily scheduled GitHub Actions workflow plus `workflow_dispatch`. Download and unpack the preceding rolling artifact before each build so unchanged and archived families can be reused. Publish only when upstream SHAs or pipeline inputs change.

Maintain a rolling GitHub Release tagged `site-artifact`, replace its assets atomically with `--clobber`, and keep generated Markdown and HTML out of the main branch.

## Consequences

- Any static hosting provider can deploy the archives by unpacking them at its web root.
- GitHub Releases provide durable prior state without growing the source branch with generated files.
- Archive checksums allow downstream consumers to verify downloads.
- The rolling Release is operational infrastructure and requires repository content-write permission in GitHub Actions.
- A failed or deleted rolling Release removes the incremental/archive source, forcing current families to rebuild and preventing recovery of already-deleted upstream families unless another copy exists.

## Alternatives considered

- **Deploy directly to GitHub Pages:** Rejected because it couples the artifact pipeline to one host.
- **Commit output to a generated branch:** Rejected because the large generated tree would create repository churn and storage growth.
- **Use only ephemeral Actions artifacts:** Rejected because their retention is insufficient for archived families.
- **Create a permanent new Release for every refresh:** Rejected initially to avoid unbounded release accumulation.
