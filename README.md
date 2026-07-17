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

The build may be large: all Markdown in every current release family is rendered and indexed.
Use `upstream.families` in `pipeline.toml` to restrict local experiments to named families.

## Output contract

The assembled site contains:

- `index.html`, redirecting to the newest current family;
- `versions.json`, consumed by the Material release selector;
- `link-report.json`, recording repaired links and generated missing-document placeholders;
- `build-manifest.json`, containing upstream SHAs, archive states, timestamps, and the pipeline fingerprint;
- `SERVICENOW-LICENSE.txt`, retaining upstream attribution and license information; and
- one directory per current or retained archived family.

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
