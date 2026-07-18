# sndocs.com

`sndocs.com` builds a host-agnostic, versioned MkDocs Material site from the public
[`ServiceNow/ServiceNowDocs`](https://github.com/ServiceNow/ServiceNowDocs) repository.
It is an independent community mirror and is not affiliated with or endorsed by ServiceNow.

The pipeline reads upstream `llms.txt`, discovers release-family branches and publications,
uses each publication's `index.md` as its navigation authority, rewrites raw GitHub Markdown
links into site links, and emits one site below `/<family>/`. A root redirect selects the newest
family. When upstream removes an old family, its last successfully built HTML remains in the
next artifact and is marked archived.

## Development

Python 3.11 or newer is required.

```shell
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e '.[test]'
.venv/bin/pytest
```

Discover the current upstream structure without building it:

```shell
.venv/bin/sndocs discover
```

For faster repeated testing, create a reusable full upstream clone during the first discovery or build, then use it offline on later runs:

```shell
.venv/bin/sndocs discover --clone-source ../ServiceNowDocs
.venv/bin/sndocs build --output site --source-repo ../ServiceNowDocs
```

The local clone must be clean and have exactly one SSH or HTTPS remote matching `upstream.repository`. Normal local runs use its committed remote-tracking refs without network access or branch switching. Refresh those refs explicitly when desired:

```shell
.venv/bin/sndocs discover --source-repo ../ServiceNowDocs --refresh-source
```

`--clone-source` fails if its destination already exists. Use `--source-repo` for an existing clone. Both source options are available on `discover` and `build`; local paths are intentionally per-run CLI inputs rather than project configuration.

Build a complete site, optionally reusing a previously unpacked artifact:

```shell
.venv/bin/sndocs build --output site --previous-site previous-site
.venv/bin/sndocs validate --site site
.venv/bin/sndocs package --site site --destination artifacts
```

Automatic build workspaces are created below the ignored `.temp/` directory and removed as each
family finishes. Supply a fresh `--work-dir` path to preserve source snapshots, transformed
Markdown, and MkDocs configuration for diagnostics; preserved workspaces can be large and are not
cleaned automatically.

Use smoke mode for a fast, strict local check of the newest family without search indexing:

```shell
.venv/bin/sndocs build --output site-smoke --source-repo ../ServiceNowDocs --smoke
.venv/bin/sndocs validate --site site-smoke
```

Smoke manifests are marked with `build_profile: smoke` and cannot be packaged as production
artifacts. Production remains the default: it renders and indexes all Markdown in every current
release family. Material navigation prunes inactive branches from each page so the full navigation
hierarchy does not multiply the generated HTML size. Use `upstream.families` in `pipeline.toml` to
restrict other local experiments to named families.

## Output contract

The assembled site contains:

- `index.html`, redirecting to the newest current family;
- `versions.json`, consumed by the Material release selector;
- schema-version-2 `link-report.json`, recording typed document and navigation repairs, generated missing-document placeholders, and omitted-image occurrences;
- `build-manifest.json`, containing the build profile, upstream SHAs, archive states, timestamps, and the pipeline fingerprint;
- `SERVICENOW-LICENSE.txt`, retaining upstream attribution and license information; and
- one directory per current or retained archived family, with a generated Material landing page at the family root.

Packaging creates `sndocs-site.tar.gz`, `sndocs-site.zip`, and a SHA-256 file for each archive.
The scheduled GitHub Actions workflow refreshes a rolling `site-artifact` GitHub Release only
when upstream SHAs or pipeline inputs change. It can also be run manually and forced to rebuild.

## Configuration

Edit `pipeline.toml` to set the site identity, canonical site URL, upstream repository and
`llms.txt` path, optional family allowlist, and archive basename. The workflow runs daily at
07:17 UTC by default; change its cron expression in `.github/workflows/build-site.yml`.

## Licensing

Pipeline code is available under the repository's MIT license. Mirrored documentation remains
copyright ServiceNow and is redistributed under the upstream Apache License 2.0. Every generated
page links to its upstream source and, when provided, its official canonical documentation page.
