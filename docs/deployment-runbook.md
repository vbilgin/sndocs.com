# Cloudflare deployment and disaster-recovery runbook

This runbook operates the latest-with-archives publication defined by [ADR-0022](adr/0022-publish-latest-with-cloudflare-releases.md), executed from an operator workstation per [ADR-0023](adr/0023-publish-from-a-local-operator-workstation.md). There is no CI: every command below runs on your own machine, and every irreversible step is something you type and watch. The public `sndocs` CLI still builds every discovered family by default; only the commands in this runbook select `build --family <latest>`.

## Release model

The private `sndocs-production` R2 bucket is the durable origin. A family tree is written once below `content/{family}/{artifact_id}/`, where the artifact ID hashes the family, upstream SHA, and pipeline fingerprint. A release has a small manifest at `releases/{release_id}.json` and five root files below `releases/{release_id}/root/`. Preview reads `pointers/preview.json`; production never reads a mutable pointer and instead receives the approved release ID as a versioned Worker variable. `pointers/production.json` is written only by `promote`, only after verification passes, and is not read by the Worker — it exists solely so a later run of this runbook can answer "what is live?" without guessing.

The rolling `site-artifact` GitHub Release is the independent recovery channel. It retains the existing monolithic artifact while adding a root archive, one archive or deterministic numbered parts for each public family, checksums, the active release manifest, and reconstruction metadata.

## Preflight

Before a rollout, confirm:

- the R2 Standard subscription and private `sndocs-production` bucket remain active;
- the bucket has neither an `r2.dev` development URL nor an R2 custom domain;
- an AWS CLI v2 profile (for example `sndocs-r2`) is configured locally with a bucket-scoped R2 access key and secret;
- `SNDOCS_R2_BUCKET`, `CLOUDFLARE_ACCOUNT_ID`, and `AWS_PROFILE` are exported in your shell (`r2.py` fails closed if the first two are unset);
- `CLOUDFLARE_API_TOKEN` is exported for `wrangler`, scoped to edit Workers scripts, versions, deployments, and routes for this account and zone, and nothing else;
- `gh` is authenticated locally with permission to manage releases on this repository;
- the `$5` and `$15` Cloudflare budget notifications still reach the operator; and
- `node` and `npm` are available for the Worker's tests and `wrangler` invocations.

Never place these credentials in repository files, shell history you intend to keep, or command-line arguments that end up logged. Export them as environment variables in your interactive shell.

Run local release tests before changing automation:

```sh
.venv/bin/pytest
npm ci --prefix worker
npm test --prefix worker
XDG_CONFIG_HOME=/tmp/sndocs-wrangler WRANGLER_LOG_PATH=/tmp/sndocs-wrangler.log npm run check --prefix worker
```

## First preview bootstrap

The first candidate must exist before preview can resolve its pointer, while the preview Worker must exist before the operator can review that candidate:

1. Run the normal publication steps below through `push-candidate`. `resolve-active` will refuse to run without `--allow-bootstrap` the first time, because `pointers/production.json` does not exist yet.
2. Deploy the preview Worker: `npm run deploy:preview --prefix worker`.
3. Confirm Cloudflare issued the `preview.sndocs.com` certificate and that the hostname returns `X-Robots-Tag: noindex, nofollow`.
4. Complete the manual preview checklist below, then run `promote`.

If preview diagnosis requires a code correction, fix it, rerun the affected steps from `push-family` onward, and discard the earlier candidate; do not promote a candidate built from a different source than the one you reviewed.

The bootstrap Worker deployment is also the recovery path if a Worker service is deleted. `npm run deploy:preview --prefix worker` only needs `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. `npm run deploy:production --prefix worker` additionally requires `RELEASE_ID` to already be set to a verified, currently-published release; it refuses to run otherwise (`worker/scripts/require-release-id.mjs`). Do not run it unless the specified release manifest and all referenced R2 objects have already been verified.

## Normal publication

Run every step below manually, in order, from the repository root.

```sh
# 0. environment (once per shell)
export AWS_PROFILE=sndocs-r2
export CLOUDFLARE_ACCOUNT_ID=<id>
export SNDOCS_R2_BUCKET=sndocs-production
export CLOUDFLARE_API_TOKEN=<token>            # wrangler only

# 1. tests
.venv/bin/pytest
npm test --prefix worker
XDG_CONFIG_HOME=/tmp/sndocs-wrangler WRANGLER_LOG_PATH=/tmp/sndocs-wrangler.log npm run check --prefix worker

# 2. discovery and the fail-closed active release
mkdir -p state
.venv/bin/sndocs discover --source ../ServiceNowDocs --json > state/discovery.json
.venv/bin/python -m sndocs.publish_cli resolve-active --output state/release-manifest.json
#   first publication only: add --allow-bootstrap

# 3. plan — pass --no-active-release only on the first publication
.venv/bin/python -m sndocs.deployment_cli plan \
  --discovery state/discovery.json \
  --active-release state/release-manifest.json \
  --output state/deployment-plan.json
LATEST=$(python3 -c "import json;print(json.load(open('state/deployment-plan.json'))['latest'])")

# 4. build and strictly validate the latest family only
.venv/bin/sndocs build --output site --source ../ServiceNowDocs --family "$LATEST"
.venv/bin/sndocs validate --site site

# 5. package, inventory with recovery metadata, immutably upload, verify
.venv/bin/python -m sndocs.publish_cli push-family \
  --site site --plan state/deployment-plan.json --handoff handoff

# 6. assemble the candidate root, retaining archived families from the active release
.venv/bin/python -m sndocs.publish_cli assemble-candidate \
  --site site --inventory handoff/family-inventory.json \
  --active-release state/release-manifest.json --candidate candidate
#   first publication only: replace the line above with --no-active-release

# 7. upload the candidate root, the manifest, and the preview pointer
.venv/bin/python -m sndocs.publish_cli push-candidate --candidate candidate
```

Before approving production, complete the manual preview checklist:

- open the preview root and latest-family page at `https://preview.sndocs.com/`;
- confirm navigation and a representative documentation page load;
- run a basic Pagefind search and open a result;
- open representative pages at desktop and mobile widths and confirm no horizontal overflow, clipped tables, uncaught page errors, console errors, or failed resource loads — this is now the only check for [SND-LAYOUT-001/002 and SND-FUNC-001/002](../src/sndocs/quality_rules/rules/), per [ADR-0024](adr/0024-validate-generated-ui-without-a-browser.md);
- confirm `X-Sndocs-Release` matches the candidate release ID printed by `push-candidate`; and
- confirm `X-Robots-Tag: noindex, nofollow`.

```sh
# 8. promote — refuses without --i-reviewed-preview, reads RELEASE_ID from the
#    manifest (never an argument), deploys, verifies over HTTP, rolls back
#    automatically on failure, and writes pointers/production.json last
.venv/bin/python -m sndocs.publish_cli promote --candidate candidate --i-reviewed-preview

# 9. recovery metadata, then the printed gh commands
mkdir -p release-assets
cp handoff/recovery/assets/* release-assets/
cp candidate/recovery/assets/* release-assets/
.venv/bin/python -m sndocs.publish_cli recovery-manifest \
  --candidate candidate --assets release-assets --print-upload-commands
#   run the printed `gh release upload` / `gh release delete-asset` commands

# 10. guarded cleanup — plan-only by default; --apply requires a rollback release
.venv/bin/python -m sndocs.publish_cli cleanup \
  --candidate candidate --rollback state/release-manifest.json
#   review the plan, then re-run with --apply once satisfied
```

`promote` is the only step that changes what production serves. Every step before it only writes to R2 prefixes that are either brand new or already immutable; every step after it is recovery bookkeeping and cleanup, neither of which affects what is currently live.

## Preview and production diagnosis

Check a release header without downloading a page body:

```sh
curl -sSI https://preview.sndocs.com/
curl -sSI https://sndocs.com/
```

Both should return `X-Sndocs-Release`; preview must also return `X-Robots-Tag: noindex, nofollow`. Test a range request with:

```sh
curl -sS -D - -o /dev/null -H 'Range: bytes=0-31' https://sndocs.com/FAMILY/pagefind/pagefind.js
```

Expect `206`, `Accept-Ranges: bytes`, an ETag, and a `Content-Range`. If the Worker returns `503`, verify the release binding or preview pointer, fetch `releases/{release_id}.json`, and confirm each family prefix and the release root exist. Do not make an R2 origin public to bypass the Worker.

If acceptance receives `403` before any `X-Sndocs-Release` header, inspect Cloudflare Security Events for the blocking product and Ray ID. Browser Integrity Check may reject default library user agents; `scripts/verify_deployment.py` sends a descriptive browser-compatible user agent so BIC can remain enabled.

## Promotion and rollback

`promote --i-reviewed-preview` is the operator's authorization to deploy the candidate Worker version; the flag itself, typed after the checklist above, is the only record that the checklist was followed. The command captures the release ID from the candidate manifest and sends `wrangler deploy` with that version to 100% of traffic.

If the post-deployment HTTP check fails, `promote` runs `wrangler rollback --env production --yes` itself and exits non-zero without writing `pointers/production.json`. For a later rollback:

1. Open Cloudflare **Workers & Pages → sndocs-production → Deployments**.
2. Identify the preceding version and verify its recorded release ID.
3. Select **Rollback** for that version. A rollback replaces production traffic at 100%; it does not mutate R2.
4. Confirm `X-Sndocs-Release` changed to the prior ID and test both its latest family and an archived family.
5. Manually restore `pointers/production.json` to the prior release ID with `aws s3api put-object` (or by re-running `promote` for that manifest once its cause is understood).
6. Record the incident and do not resume cleanup or publication until the cause is understood.

The immediately preceding release and every family it references are protected by cleanup. Do not delete or rename the R2 bucket binding between deployment and rollback.

## Recovery from GitHub Release assets

Download `release-manifest.json`, `reconstruction.json`, `recovery-assets.sha256`, every `sndocs-root.tar.gz` part, and the archive or numbered parts named for every family in `reconstruction.json`. Verify the per-part checksums before concatenation and the complete archive checksum before extraction.

For one archive, the internal tool reconstructs and verifies safely:

```sh
jq '.families.FAMILY' reconstruction.json > family-recovery.json
python -m sndocs.deployment_cli reconstruct \
  --metadata family-recovery.json \
  --assets downloaded-assets \
  --destination restored-site/FAMILY
```

Reconstruct the root archive directly into `restored-site`, then reconstruct each family into its matching subdirectory. Run:

```sh
.venv/bin/sndocs validate --site restored-site
```

The result is host-agnostic and can be uploaded to another static host. Never restore an archived family by rebuilding from a different upstream SHA. If a checksum, part, or manifest is absent, stop: incomplete recovery fails closed.

## Credential rotation

For R2 credentials, create a replacement bucket-scoped read/write key, update your local AWS profile, run a no-change publication plan (steps 1–2 above) plus a read-only bucket listing (`aws s3api list-objects-v2 --bucket sndocs-production --max-items 1`), and then revoke the old key. For the Worker token, create the replacement least-privilege token, export it as `CLOUDFLARE_API_TOKEN`, run both Wrangler dry runs (`npm run check --prefix worker`), redeploy preview only if a deploy test is required, and then revoke the old token. Never print credentials or place them in repository files, shell history you intend to keep, workflow artifacts, Worker variables, or release metadata.

## Cleanup

Cleanup is separate from publication logic even though it runs as the last step of the same manual sequence. It always writes `candidate/cleanup-plan.json` before deletion, whether or not `--apply` is passed. The first successful publication is dry-run only because no rollback release exists yet, and `cleanup` itself refuses `--apply` without one.

For later publications, cleanup may delete only objects that are unreferenced and older than 14 days, and it requires that every protected release's family records carry recovery metadata (`require_recovery=True` by default) — pass `--allow-missing-recovery` only for a release published before recovery metadata was recorded. It must refuse to select:

- active or preceding release manifests and root files;
- any family artifact referenced by either release;
- every public archived-family artifact, including its recovery prefix;
- active inventory and recovery metadata;
- `pointers/preview.json` or `pointers/production.json`; or
- any object still inside the grace period.

Review any unexpectedly large deletion plan before retrying a failed cleanup. Never substitute an unscoped `aws s3 rm --recursive`.

## Security and cost rollout

After apex, preview, and `www` routing work:

1. enable Always Use HTTPS and minimum TLS 1.2;
2. enable the Free managed WAF ruleset and Bot Fight Mode;
3. introduce the conservative rate rule with verified bots excluded;
4. observe Worker errors, requests, R2 Class A/B operations, cache-hit behavior, and storage growth for 48 hours; and
5. enable HSTS with a one-month max age, without `includeSubDomains` or preload.

A scheduled trigger is intentionally out of scope: publication is deliberately manual and operator-driven per [ADR-0023](adr/0023-publish-from-a-local-operator-workstation.md).

Unexpected R2 Class B operations usually indicate poor edge caching; unexpected Class A operations usually indicate repeated publication or list activity. Storage should grow by one new family artifact when latest changes and by one replacement latest artifact when its SHA or pipeline changes. Workers Paid, a larger local build machine, Cache Reserve, R2 Infrequent Access, or any other paid expansion requires a separate explicit decision.
