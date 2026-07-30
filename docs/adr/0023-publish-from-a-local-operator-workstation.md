# ADR-0023: Publish from a local operator workstation

- **Status:** Accepted
- **Date:** 2026-07-29
- **Decision owner:** Victor Bilgin
- **Supersedes:** [ADR-0022](0022-publish-latest-with-cloudflare-releases.md) only for execution environment and approval gate

## Context

The publication workflow ran entirely inside GitHub Actions, with `.github/workflows/build-site.yml` as the only place that performed R2 uploads, downloads, listings, and deletions: every `aws s3`/`aws s3api` call, the `pointers/preview.json` generation, the `recovery.prefix` injection into a family inventory, and the `reconstruction.json`/checksum assembly existed only as inline shell and `jq` in workflow YAML. No Python module performed any of it. Protected-environment approval stood in for a manual preview review.

The project has moved to building and publishing from the operator's own machine, with no CI. That removes the free machine that ran R2 I/O and the GitHub Environment that recorded approval, but changes nothing about the release model ADR-0022 established: immutable per-family content prefixes keyed by artifact ID, small versioned release manifests, a mutable preview pointer with a pinned production release ID, deterministic recovery archives, and grace-windowed cleanup.

A second problem surfaced while designing the replacement: `plan_latest_release`'s `active_release` argument silently accepted `None` for a *missing* input, not just a genuinely absent prior release. A typo'd or forgotten `--active-release` path therefore planned an "initial" release, and `_retained_families` (`deployment.py`) then retains only the newly built family — every archived family silently disappears from `versions.json`. The only prior source of truth for "what is live" was cross-checking the rolling GitHub Release against R2, which required both `gh` and network access on every run and still left a caller free to omit it.

## Decision

Move every R2 upload, download, listing, and deletion into a new `src/sndocs/r2.py`: a thin wrapper around the `aws` CLI, invoked via `subprocess` with an injectable runner for testing. Use the `aws` CLI rather than boto3 because the existing verification contract in `deployment.py` (`verify_uploaded_inventory`, `verify_uploaded_tree`, `plan_cleanup`'s batch shape) is already `list-objects-v2`/`delete-objects`-shaped, because `aws s3 cp --recursive` already performs the concurrent multipart transfer a multi-gigabyte family tree needs without new project code owning that risk, and because the R2 checksum-header workaround the workflow used (`AWS_REQUEST_CHECKSUM_CALCULATION`/`AWS_RESPONSE_CHECKSUM_VALIDATION`) is a documented environment variable rather than something to re-derive against botocore.

Add `src/sndocs/publish_cli.py`, invoked as `python -m sndocs.publish_cli`, as the only module that performs irreversible side effects. It stays separate from `deployment_cli.py`, which remains a pure file-in/file-out shim over the pure functions in `deployment.py`. Every publication capability the workflow previously expressed as shell — the write-once immutability guard, the manifest-uploaded-last-then-read-back-and-compared sequencing, `pointers/preview.json` generation, recovery-asset packaging and upload, `wrangler deploy`/`rollback`, and cleanup batching — becomes a `publish_cli` subcommand backed by pure helpers added to `deployment.py` (`preview_pointer`, `production_pointer`, `build_reconstruction`, `recovery_checksum_manifest`).

Introduce `pointers/production.json`, written only by `promote` and only after the post-deployment HTTP verification passes, as the fail-closed answer to "what is live". `resolve-active` reads it and has exactly three outcomes: the pointer names a release that exists and validates, in which case that manifest becomes the active release; the pointer is absent and `--allow-bootstrap` was passed, for the first release only; or the pointer is absent without that flag, which is a hard failure rather than a silent "initial" plan. The Worker must never read this key — production continues to pin its release through the versioned `RELEASE_ID` Worker variable, exactly as ADR-0022 specified; the pointer exists only for the human-driven planning step that used to be a GitHub Actions cross-check.

Independently of the execution-environment move, fix the underlying fail-open defects everywhere they exist: `deployment_cli._read` now raises on a missing path instead of returning `None`; `plan` and `assemble` require an explicit `--active-release` or `--no-active-release`; `assemble_candidate` requires `active_root` and `active_release` together in both directions; `build_family_inventory` derives its `recovery.prefix` internally rather than accepting one from a caller (removing the class of error the workflow's `jq --arg prefix` injection invited); and `plan_cleanup` gains `require_recovery: bool = True`, refusing to plan when a protected release's family record lacks recovery metadata, because the prior `.get("recovery", {})` guard failed open and would have made recovery assets deletable.

The protected-environment approval that used to gate `promote-production` becomes `promote --i-reviewed-preview`: the flag is refused without printing the manual preview checklist first, and it is the only record that the checklist was followed. `worker/package.json` gains a `deploy:production` script that refuses to run unless `RELEASE_ID` is a 64-hex-character digest, so a hand-typed deploy cannot leave the Worker at the `BOOTSTRAP_REQUIRED` sentinel — which the Worker already turns into a clean 503 rather than serving the wrong release, per its existing fail-closed manifest validation.

The rolling GitHub Release recovery channel is unchanged in kind: `python -m sndocs.publish_cli recovery-manifest` produces `reconstruction.json` and `recovery-assets.sha256` in Python instead of `jq`, fixing two defects the shell version had — a retained family with no recovery archive silently serialized to `null` with no record that it happened (now surfaced as `families_without_recovery`), and checksums were ordered by shell glob rather than sorted by name. The operator runs the printed `gh release upload`/`delete-asset` commands by hand; `gh` stays out of Python.

## Consequences

- Publication has no CI dependency and no GitHub Environment; the operator's own `~/.aws` profile and local `wrangler`/`gh` installs are the only required tooling.
- "What is live" has a single explicit, versioned answer in R2 (`pointers/production.json`) instead of a runtime cross-check against a separate recovery channel, and every code path that reads it fails closed rather than silently planning an initial release.
- Recovery-asset protection in cleanup planning is now enforced rather than merely intended; a release assembled without recovery metadata cannot be cleaned up against until that is fixed or explicitly overridden.
- `deployment.py` and `deployment_cli.py` remain pure and fully unit-testable without a live bucket; `r2.py` and `publish_cli.py` carry all network and subprocess risk and are tested with an injected fake runner.
- The manual preview checklist is now enforced by a required flag rather than recorded implicitly by a GitHub Environment approval click; there is no automated substitute for a human looking at the preview.
- The operator is responsible for AWS/R2 credential hygiene and for running the runbook's verification ladder before every publication that this project previously ran automatically on every push.

## Alternatives considered

- **boto3 instead of the `aws` CLI:** Rejected — it adds botocore, s3transfer, and jmespath to a six-dependency pipeline, and would require reimplementing the concurrent multipart transfer and R2 checksum handling the `aws` CLI already provides, in the one code path most able to destroy published data.
- **Keep `deployment_cli` as the home for R2 I/O:** Rejected — mixing subprocess/network orchestration into the module that also computes SHA-256 digests and validates manifests would make the twelve existing pure subcommands harder to reason about and to test without a live bucket.
- **A public `sndocs publish` command:** Rejected — `sndocs`'s CLI safety contract (ADR-0013) is written for the idempotent build/validate/package surface; publication's irreversible side effects belong in an explicitly internal, runbook-driven entry point instead.
- **Keep "newest `releases/*.json`" as the active-release signal:** Rejected — a failed or abandoned promote leaves a candidate manifest under `releases/` that is not live, so "newest" is not fail-closed; an explicit pointer, written only after verification, is.

## Related decisions

- [ADR-0022](0022-publish-latest-with-cloudflare-releases.md) defines the release model, immutability, retention, and Worker behavior that this decision leaves unchanged.
- [ADR-0013](0013-simplify-and-harden-cli.md) defines the public CLI safety contract that publication intentionally sits outside of.
- [Deployment runbook](../deployment-runbook.md) documents the operator-facing commands this decision introduces.
