"""Post-render HTML minification pass for the built site.

`sndocs build --minify` runs this after the MkDocs render and before Pagefind
indexing: every rendered ``site_dir/**/*.html`` file is re-emitted through
``minify-html`` with the deliberately conservative option set below, shrinking
the built site on disk while keeping each page semantically identical. The walk
is parallelised across a process pool, mirroring `sndocs.normalize`'s
fork-context + per-worker-globals pattern.

A file that raises while minifying is left exactly as MkDocs produced it, added
to a tally, and surfaced by the caller; the build still succeeds.
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import minify_html

# The one conservative minify profile, defined here so `sndocs.minify_check`
# (#33) imports it rather than keeping its own copy. Every keyword `minify-html`
# accepts is pinned explicitly — even where the value matches the current library
# default — so a future release flipping a default can't silently change what the
# built site looks like (`test_minify_options_are_the_conservative_profile` locks
# the exact dict):
#
#   * keep_closing_tags / keep_html_and_head_opening_tags — leave the tag shape
#     MkDocs emitted intact; only inter-tag whitespace and comments go.
#   * keep_comments off — strip HTML comments (the default). NOTE: this pass runs
#     *before* Pagefind indexing (see `sndocs.build.build_site`), so an
#     HTML-comment Pagefind directive (`<!-- pagefind-ignore -->`) would be gone
#     before Pagefind sees it. The corpus/theme use none today; if that changes,
#     use the attribute form (`data-pagefind-ignore`) instead.
#   * minify_css / minify_js off — never touch stylesheet or script bodies.
#   * minify_doctype off — leave `<!DOCTYPE html>` untouched.
#   * every allow_* relaxation off — in particular allow_optimal_entities stays
#     off so an `href` query string like `?x=1&sect=2&para=3` is never re-parsed
#     into `§`/`¶` (`&sect`/`&para` are valid entity names without a semicolon).
#   * every keep_*/preserve_*/remove_* left at its safe default, pinned so it
#     stays there.
MINIFY_OPTIONS: dict[str, bool] = {
    "keep_closing_tags": True,
    "keep_html_and_head_opening_tags": True,
    "keep_comments": False,
    "keep_input_type_text_attr": False,
    "keep_ssi_comments": False,
    "minify_css": False,
    "minify_js": False,
    "minify_doctype": False,
    "preserve_brace_template_syntax": False,
    "preserve_chevron_percent_template_syntax": False,
    "remove_bangs": False,
    "remove_processing_instructions": False,
    "allow_noncompliant_unquoted_attribute_values": False,
    "allow_optimal_entities": False,
    "allow_removing_spaces_between_attributes": False,
}


def minify_html_text(html: str) -> str:
    """Minify one HTML document string with the conservative `MINIFY_OPTIONS`."""
    return minify_html.minify(html, **MINIFY_OPTIONS)


@dataclass
class MinifyReport:
    """Outcome of a `minify_site` pass over the rendered site."""

    total_files: int = 0
    minified_files: int = 0
    failed_files: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def bytes_saved(self) -> int:
        return self.bytes_before - self.bytes_after


def _minify_path(absolute: Path, site_root: Path) -> dict[str, object]:
    relative = absolute.relative_to(site_root).as_posix()
    original = b""
    try:
        original = absolute.read_bytes()
        candidate = minify_html_text(original.decode("utf-8")).encode("utf-8")
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        # A poison file — unreadable (OSError), not UTF-8 (UnicodeDecodeError),
        # or minify-html hitting a Rust panic (pyo3 PanicException is a
        # BaseException, not an Exception) — is left byte-for-byte as MkDocs
        # produced it, tallied, and reported; the build still succeeds.
        return {
            "path": relative,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "bytes_before": len(original),
            "bytes_after": len(original),
        }
    # Only rewrite when minification actually shrinks the file, so the pass can
    # never leave a page larger than MkDocs rendered it (and reported savings
    # can never go negative).
    if len(candidate) < len(original):
        absolute.write_bytes(candidate)
        bytes_after = len(candidate)
    else:
        bytes_after = len(original)
    return {
        "path": relative,
        "ok": True,
        "error": None,
        "bytes_before": len(original),
        "bytes_after": bytes_after,
    }


_site_root: Path


def _init_worker(site_root: str) -> None:
    global _site_root
    _site_root = Path(site_root)


def _minify_one_worker(relative_text: str) -> dict[str, object]:
    return _minify_path(_site_root / relative_text, _site_root)


def minify_site(site_dir: Path, workers: int | None = None) -> MinifyReport:
    """Minify every ``*.html`` file under `site_dir` in place, parallelised across
    `workers` processes (default: available CPU count). Returns a `MinifyReport`;
    files that raise while minifying are left untouched and recorded in it."""
    site_dir = site_dir.resolve()
    if not site_dir.is_dir():
        raise FileNotFoundError(f"{site_dir} does not exist.")
    workers = workers if workers is not None else max(1, os.cpu_count() or 1)
    if workers < 1:
        raise ValueError("workers must be at least 1")

    html_files = sorted(
        (p.relative_to(site_dir) for p in site_dir.rglob("*.html") if p.is_file()),
        key=lambda p: p.as_posix(),
    )

    if workers == 1 or len(html_files) <= 1:
        results = [_minify_path(site_dir / p, site_dir) for p in html_files]
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("fork"),
            initializer=_init_worker,
            initargs=(str(site_dir),),
        ) as executor:
            results = list(
                executor.map(_minify_one_worker, (p.as_posix() for p in html_files), chunksize=16)
            )

    report = MinifyReport()
    for result in results:
        report.total_files += 1
        report.bytes_before += int(result["bytes_before"])
        report.bytes_after += int(result["bytes_after"])
        if result["ok"]:
            report.minified_files += 1
        else:
            report.failed_files += 1
            report.failures.append((str(result["path"]), str(result["error"])))
    return report
