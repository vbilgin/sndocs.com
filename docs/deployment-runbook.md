# Cloudflare deployment and disaster-recovery runbook

This runbook operates the latest-with-archives publication defined by [ADR-0022](adr/0022-publish-latest-with-cloudflare-releases.md). The public `sndocs` CLI still builds every discovered family by default; only the Cloudflare publication workflow selects `build --family <latest>`.

## Release model

The private `sndocs-production` R2 bucket is the durable origin. A family tree is written once below `content/{family}/{artifact_id}/`, where the artifact ID hashes the family, upstream SHA, and pipeline fingerprint. A release has a small manifest at `releases/{release_id}.json` and five root files below `releases/{release_id}/root/`. Preview reads `pointers/preview.json`; production never reads a mutable pointer and instead receives the approved release ID as a versioned Worker variable.

The rolling `site-artifact` GitHub Release is the independent recovery channel. It retains the existing monolithic artifact while adding a root archive, one archive or deterministic numbered parts for each public family, checksums, the active release manifest, and reconstruction metadata.

## Preflight

Before a rollout, confirm:

- the R2 Standard subscription and private `sndocs-production` bucket remain active;
- the bucket has neither an `r2.dev` development URL nor an R2 custom domain;
- the `preview` GitHub Environment exposes `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`;
- the `production` GitHub Environment exposes `CLOUDFLARE_API_TOKEN`, requires approval, and restricts deployment branches;
- `CLOUDFLARE_ACCOUNT_ID` is an Actions variable available to both environments;
- the Worker token can edit Workers scripts, versions, deployments, and routes for this account and zone, but has no unrelated permissions; and
- the `$5` and `$15` Cloudflare budget notifications still reach the operator.

Run local release tests before changing automation:

```sh
.venv/bin/pytest
npm ci --prefix worker
npm test --prefix worker
XDG_CONFIG_HOME=/tmp/sndocs-wrangler WRANGLER_LOG_PATH=/tmp/sndocs-wrangler.log npm run check --prefix worker
```

## First preview bootstrap

The first candidate must exist before preview can resolve its pointer, while the preview Worker must exist before preview acceptance can pass:

1. Manually run **Publish latest documentation release**.
2. Let `test-and-plan`, `build-latest`, and `assemble-candidate` complete. The first run may stop at `validate-preview` because `preview.sndocs.com` has not been bootstrapped.
3. Confirm the candidate release ID in the workflow summary and verify that `pointers/preview.json` contains it with the R2 object browser.
4. Run **Bootstrap Cloudflare Worker**, choose `preview`, and approve its protected `production` Environment.
5. Confirm Cloudflare issued the `preview.sndocs.com` certificate and that the hostname returns `X-Robots-Tag: noindex, nofollow`.
6. If the missing preview Worker was the only failure and no code correction was required, re-run the failed jobs of the original publication run. This preserves its already verified candidate rather than rebuilding it.

GitHub reruns remain pinned to the original commit. If preview diagnosis requires a code correction, do not rerun that publication: commit and push the correction, bootstrap preview from the corrected commit, and start a new publication run so preview validation and production deployment use the same fixed source.

The bootstrap workflow is also the recovery path if a Worker service is deleted. Do not choose its `production` target unless the specified release manifest and all referenced R2 objects have already been verified.

## Normal publication

Run **Publish latest documentation release** manually while rollout is being proven. The workflow:

1. runs all Python and Worker tests, discovers the upstream latest family, and compares it with the active release manifest from the rolling GitHub Release;
2. exits successfully when latest family, source SHA, and pipeline fingerprint are unchanged;
3. builds only latest on a standard runner and terminates the build if additional disk consumption reaches 12 GiB;
4. uploads the family tree to a new immutable prefix and verifies the exact remote key and byte inventory;
5. assembles root metadata from the new latest record and already published records only;
6. uploads and verifies the release root, uploads the release manifest last, and updates the preview pointer only after verification;
7. checks preview navigation, archived families, ranges, Pagefind initialization, release headers, 404s, and no-index behavior;
8. pauses at the protected `production` Environment;
9. deploys a production Worker version containing the candidate release ID at 100% traffic and automatically invokes Wrangler rollback if immediate smoke checks fail;
10. updates only the changed-family and rolling root recovery assets; and
11. creates a cleanup plan, retaining the active and rollback releases, every archived family, and all objects in the 14-day grace window.

Inspect the workflow summaries before approving production. The candidate release ID in preview must match the proposed production ID. A scheduled trigger is deliberately absent until the first two successful production releases and the observation period are complete.

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

If acceptance receives `403` before any `X-Sndocs-Release` header, inspect Cloudflare Security Events for the blocking product and Ray ID. Browser Integrity Check may reject default library user agents; the deployment verifier sends a descriptive browser-compatible user agent so BIC can remain enabled.

## Promotion and rollback

Production approval is authorization to deploy the candidate Worker version. The deployment captures its release ID and R2 binding, and `wrangler deploy` sends that version to 100% of traffic.

If an immediate smoke check fails, the workflow runs `wrangler rollback --env production --yes`. For a later rollback:

1. Open Cloudflare **Workers & Pages → sndocs-production → Deployments**.
2. Identify the preceding version and verify its recorded release ID.
3. Select **Rollback** for that version. A rollback replaces production traffic at 100%; it does not mutate R2.
4. Confirm `X-Sndocs-Release` changed to the prior ID and test both its latest family and an archived family.
5. Record the incident and do not resume cleanup or publication until the cause is understood.

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

For R2 credentials, create a replacement bucket-scoped read/write key, update both preview-environment secrets, run a no-change publication plan plus a read-only bucket listing, and then revoke the old key. For the Worker token, create the replacement least-privilege token, update the production-environment secret, run both Wrangler dry runs, bootstrap preview only if a deploy test is required, and then revoke the old token. Never print credentials or place them in repository files, workflow artifacts, Worker variables, or release metadata.

## Cleanup

Cleanup is separate from publication logic even though it is a dependent workflow job. It always writes `cleanup-plan.json` before deletion. The plan digest and resulting storage totals are retained as workflow evidence. The first successful publication is dry-run only because no rollback release exists.

For later publications, cleanup may delete only objects that are unreferenced and older than 14 days. It must refuse to select:

- active or preceding release manifests and root files;
- any family artifact referenced by either release;
- every public archived-family artifact, including its recovery prefix;
- active inventory and recovery metadata;
- `pointers/preview.json`; or
- any object still inside the grace period.

Review any unexpectedly large deletion plan before retrying a failed cleanup. Never substitute an unscoped `aws s3 rm --recursive`.

## Security and cost rollout

After apex, preview, and `www` routing work:

1. enable Always Use HTTPS and minimum TLS 1.2;
2. enable the Free managed WAF ruleset and Bot Fight Mode;
3. introduce the conservative rate rule with verified bots excluded;
4. observe Worker errors, requests, R2 Class A/B operations, cache-hit behavior, and storage growth for 48 hours;
5. enable HSTS with a one-month max age, without `includeSubDomains` or preload; and
6. add the daily `07:17 UTC` schedule to the publication workflow only after two successful releases and a proven rollback.

Unexpected R2 Class B operations usually indicate poor edge caching; unexpected Class A operations usually indicate repeated publication or list activity. Storage should grow by one new family artifact when latest changes and by one replacement latest artifact when its SHA or pipeline changes. Workers Paid, a larger GitHub runner, Cache Reserve, R2 Infrequent Access, or any other paid expansion requires a separate explicit decision.
