"""Re-validate the normalizer's render-equivalence guarantees against the *real*
target rendering engine.

The normalizer (`sndocs.normalize`) only applies its "safe" cosmetic cleanup
(redundant-escape removal, trailing-whitespace and excess-blank-line collapsing)
and its simple HTML-table -> pipe-table conversion when the change is
render-equivalent under `markdown-it-py`. But the site is actually rendered by
MkDocs with **Python-Markdown** plus the extensions configured in `mkdocs.yml`.
Issue #14 asks us to confirm the guarantee still holds under that engine, and to
tune the `mkdocs.yml` extension bundle if it doesn't.

This module builds a Python-Markdown instance from the `mkdocs.yml` extension
bundle, resolved via `mkdocs.config.load_config` so it matches a real
`mkdocs build`, and re-checks every render-gated decision the normalizer makes:

* `check_body()` compares a file's source and normalized bodies under the engine
  and reports a `cosmetic-divergence` (the normalizer's cleanup gate passes
  under `markdown-it-py` but Python-Markdown renders it differently, beyond the
  known-benign stray-backslash and whitespace noise) or a `table-not-rendered`
  (the normalized body strands a pipe-table delimiter row in prose).
* `sweep()` runs `check_body()` across a set of corpus files and aggregates.
* `python -m sndocs.engine_check` runs the sweep from the CLI for the full
  `.sndocs/repo` corpus (or a random sample, or an explicit list of paths).

Findings from the one-time issue-#14 sweep, and the final extension bundle they
motivated, are recorded in `docs/adr/0001-rendering-engine-revalidation.md`.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown_it import MarkdownIt

from sndocs.normalize import (
    MARKDOWN_SUFFIXES,
    cosmetic_candidate,
    normalize_text,
    parser as markdown_it_parser,
    split_front_matter,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "mkdocs.yml"
DEFAULT_CORPUS = REPO_ROOT / ".sndocs" / "repo"

# A pipe-table delimiter row that leaked into rendered prose instead of becoming
# a real table (e.g. `<p>| --- | --- |</p>`).
_LEAKED_DELIMITER_RE = re.compile(r"<p>[^<]*\|[ \t]*:?-{3,}:?[ \t]*\|")
# A literal `\(` / `\)` / `\_` that survived into rendered HTML. Python-Markdown
# only leaves these unresolved inside raw-HTML passthrough (it resolves them
# everywhere a CommonMark escape applies), where the normalizer's cleanup would
# *remove* a visible stray backslash — an improvement, not a regression. Folding
# them document-wide is safe and targets exactly ADR 0001's finding 2.
_BENIGN_ESCAPE_RE = re.compile(r"\\([()_])")
# Only *newline-bearing* inter-tag whitespace — i.e. block serialisation, not a
# deliberate space between two inline elements — so a real inline-boundary
# divergence is still surfaced.
_INTERTAG_NEWLINE_RE = re.compile(r">[ \t]*\n[ \t\n]*<")
_BLANK_RUN_RE = re.compile(r"\n[ \t]*\n[ \t\n]*")


def _canonical_render(html: str) -> str:
    """Fold out the two known-benign render differences — a literal `\\(`/`\\)`/
    `\\_` the engine left in raw-HTML passthrough, and block-serialisation
    whitespace between blocks — so only *meaningful* divergence remains."""
    html = _BENIGN_ESCAPE_RE.sub(r"\1", html)
    html = _INTERTAG_NEWLINE_RE.sub("><", html)
    return _BLANK_RUN_RE.sub("\n\n", html).strip()


def configured_extensions(config_file: Path = DEFAULT_CONFIG) -> tuple[list[str], dict]:
    """The extension list + per-extension config MkDocs hands to Python-Markdown
    for `config_file`, resolved exactly as `mkdocs build` would.

    Uses the public `mkdocs.config.load_config`; `docs_dir`/`site_dir` are pointed
    at throwaway temp dirs so it resolves without the corpus on disk."""
    import tempfile
    from mkdocs.config import load_config

    with tempfile.TemporaryDirectory() as tmp:
        docs_dir = Path(tmp) / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# stub\n", encoding="utf-8")
        cfg = load_config(
            str(config_file),
            docs_dir=str(docs_dir),
            site_dir=str(Path(tmp) / "site"),
        )
    return list(cfg["markdown_extensions"]), dict(cfg["mdx_configs"] or {})


def python_markdown(config_file: Path = DEFAULT_CONFIG) -> markdown.Markdown:
    """A Python-Markdown instance mirroring what `mkdocs build` renders with."""
    extensions, configs = configured_extensions(config_file)
    return markdown.Markdown(extensions=extensions, extension_configs=configs)


def render_python_markdown(md: markdown.Markdown, text: str) -> str:
    md.reset()
    return md.convert(text).rstrip("\n")


def render_markdown_it(md: MarkdownIt, text: str) -> str:
    return md.render(text).rstrip("\n")


@dataclass
class Finding:
    """One way a file's normalization diverges under the real engine."""

    path: str
    kind: str  # "cosmetic-divergence" | "table-not-rendered"
    detail: str


def check_body(
    path: str,
    source_body: str,
    normalized_body: str | None = None,
    *,
    markdown_it: MarkdownIt,
    python_md: markdown.Markdown,
) -> list[Finding]:
    """Compare the source and normalized bodies (front matter already stripped)
    under the real engine and report divergences.

    * ``cosmetic-divergence`` — the normalizer's cosmetic cleanup gate passes
      under `markdown-it-py` but Python-Markdown renders the cleaned body
      differently, beyond the known-benign stray-backslash removal and
      insignificant whitespace (see `_canonical_render`).
    * ``table-not-rendered`` — the normalized body leaves a pipe-table delimiter
      row stranded in prose (`<p>| --- | --- |`) that the source did not, i.e. a
      table the source engine accepted no longer renders as one.

    `normalized_body` defaults to running `normalize_text` on `source_body` so
    callers with only the source don't have to."""
    findings: list[Finding] = []

    if normalized_body is None:
        normalized_full, _, _ = normalize_text(
            source_body, markdown_it, path, frozenset(), audit_idempotence=False
        )
        _, normalized_body, _ = split_front_matter(normalized_full)

    source_html = render_python_markdown(python_md, source_body)

    # 1. Cosmetic cleanup gate.
    cosmetic, _ = cosmetic_candidate(source_body)
    if cosmetic != source_body and render_markdown_it(markdown_it, cosmetic) == render_markdown_it(
        markdown_it, source_body
    ):
        cosmetic_html = render_python_markdown(python_md, cosmetic)
        if cosmetic_html != source_html and _canonical_render(cosmetic_html) != _canonical_render(source_html):
            findings.append(
                Finding(
                    path,
                    "cosmetic-divergence",
                    "markdown-it renders cosmetic cleanup as equivalent; Python-Markdown "
                    "differs beyond stray-backslash removal and whitespace",
                )
            )

    # 2. Pipe-table delimiter stranded in the normalized output but not the source.
    normalized_html = (
        source_html if normalized_body == source_body else render_python_markdown(python_md, normalized_body)
    )
    if _LEAKED_DELIMITER_RE.search(normalized_html) and not _LEAKED_DELIMITER_RE.search(source_html):
        findings.append(
            Finding(
                path,
                "table-not-rendered",
                "a pipe-table delimiter row renders as prose (`<p>| --- |`) under Python-Markdown",
            )
        )

    return findings


@dataclass
class SweepReport:
    checked: int
    findings: list[Finding]

    @property
    def clean(self) -> bool:
        return not self.findings

    def summary(self) -> str:
        by_kind: dict[str, int] = {}
        for finding in self.findings:
            by_kind[finding.kind] = by_kind.get(finding.kind, 0) + 1
        lines = [f"checked {self.checked} file(s); {len(self.findings)} finding(s)"]
        for kind, count in sorted(by_kind.items()):
            lines.append(f"  {count:5d}  {kind}")
        return "\n".join(lines)


def _body(text: str) -> str:
    _, body, _ = split_front_matter(text.replace("\r\n", "\n").replace("\r", "\n"))
    return body


def sweep(
    paths: list[Path],
    corpus_root: Path,
    *,
    normalized_root: Path | None = None,
    config_file: Path = DEFAULT_CONFIG,
) -> SweepReport:
    """Run `check_body()` for every file in `paths` (each relative to `corpus_root`).

    If `normalized_root` is given, the already-normalized body is read from there;
    otherwise `check_body()` re-normalizes each source in-process."""
    markdown_it = markdown_it_parser()
    python_md = python_markdown(config_file)
    findings: list[Finding] = []
    checked = 0
    for relative in paths:
        source_body = _body((corpus_root / relative).read_text(encoding="utf-8"))
        normalized_body = None
        if normalized_root is not None:
            normalized_path = normalized_root / relative
            if normalized_path.is_file():
                normalized_body = _body(normalized_path.read_text(encoding="utf-8"))
        findings.extend(
            check_body(
                relative.as_posix(),
                source_body,
                normalized_body,
                markdown_it=markdown_it,
                python_md=python_md,
            )
        )
        checked += 1
    return SweepReport(checked=checked, findings=findings)


def _discover(corpus_root: Path) -> list[Path]:
    return sorted(
        (
            p.relative_to(corpus_root)
            for p in corpus_root.rglob("*")
            if p.is_file() and p.suffix.lower() in MARKDOWN_SUFFIXES
        ),
        key=lambda p: p.as_posix(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="Corpus root (default: .sndocs/repo).")
    parser.add_argument(
        "--normalized",
        type=Path,
        default=REPO_ROOT / ".sndocs" / "normalized",
        help="Normalized-output root; used when present, else sources are re-normalized in-process.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="mkdocs.yml (default: repo root).")
    parser.add_argument("--sample", type=int, default=None, help="Check a random sample of N files instead of all.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for --sample (default: 0).")
    parser.add_argument("--show", type=int, default=20, help="Max findings to print in detail (default: 20).")
    parser.add_argument("paths", nargs="*", type=Path, help="Explicit corpus-relative paths to check.")
    args = parser.parse_args(argv)

    if not args.corpus.is_dir():
        parser.error(f"corpus root does not exist: {args.corpus} (run `sndocs fetch` first)")

    if args.paths:
        paths = list(args.paths)
        missing = [p for p in paths if not (args.corpus / p).is_file()]
        if missing:
            parser.error(f"not found under {args.corpus}: {', '.join(str(p) for p in missing)}")
    else:
        paths = _discover(args.corpus)
        if args.sample is not None:
            paths = random.Random(args.seed).sample(paths, min(args.sample, len(paths)))
            paths.sort(key=lambda p: p.as_posix())

    normalized_root = args.normalized if args.normalized and args.normalized.is_dir() else None
    report = sweep(paths, args.corpus, normalized_root=normalized_root, config_file=args.config)
    print(report.summary())
    for finding in report.findings[: args.show]:
        print(f"\n{finding.path}\n  {finding.kind}: {finding.detail}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
