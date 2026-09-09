"""Before/after equivalence + size-delta check for the HTML minification pass.

`sndocs build --minify` (issue #32) re-emits every rendered page through
``minify-html`` with the deliberately conservative option set in
`sndocs.minify.MINIFY_OPTIONS`. With that profile the rendered DOM should be
*structurally identical* before and after minification — only inter-element
whitespace text nodes (the block-serialisation newlines MkDocs emits between
tags) may differ. Anything else is a regression in the minifier or a corpus
construct the conservative profile does not actually keep safe.

This module is the committed, re-runnable guard for that guarantee, mirroring
`sndocs.engine_check` in shape and role. It takes a built ``.sndocs/site/``,
minifies each sampled page with the *same* profile the build uses (imported from
`sndocs.minify` — never re-declared here), and reports:

1. **Semantic divergence** between the original and minified page, across five
   strict checks:

   * ``tag-structure`` — the element tree (tag name + nesting of every element,
     in document order) is identical, so any rename, drop, insertion or
     re-parenting is caught. Comment nodes are ignored (`keep_comments` is off,
     so their removal is expected). Attributes other than ``href`` / ``src`` are
     deliberately *not* compared: the conservative profile makes safe attribute
     edits — collapsing whitespace in a space-separated ``class``, dropping a
     redundant ``type="text"`` — that Material for MkDocs triggers on nearly
     every page and that are not divergences.
   * ``text-content`` — every text node, with internal whitespace collapsed, is
     identical in document order. A purely-whitespace text node (inter-element
     whitespace) is allowed to appear or vanish; a non-whitespace one is not.
   * ``link-attr`` — every ``href`` / ``src`` attribute value is byte-identical.
     Guards `minify-html` issue #169: a named-entity-prefix query param such as
     ``?x=1&sect=2&para=3`` must never be re-parsed into ``§`` / ``¶``.
   * ``inline-svg`` — every inline ``<svg>`` subtree is structurally identical,
     attributes included (``minify-html`` leaves SVG-foreign content opaque, so
     a ``viewBox`` / ``d`` change there really is a regression). Guards
     ``minify-html`` issue #192: a self-closing inline SVG emitted unclosed
     re-parents everything after it.
   * ``pre-text`` — every ``<pre>`` block has identical text after
     entity-decoding. Tolerates the benign ``<`` -> ``&lt;`` re-encode (both
     sides are decoded before comparison); catches real whitespace loss.

   plus ``parse-failure`` for a minified page ``lxml`` cannot parse at all.

2. **Aggregate size reduction** over the sample: before/after byte totals and
   percentage reduction.

``python -m sndocs.minify_check --sample N --seed S`` runs the check from the
CLI, with the same ``--sample`` / ``--seed`` / explicit-paths interface as
`sndocs.engine_check`. Exit code is non-zero when any divergence outside
inter-element whitespace is found. A large-``N`` run also stands in for the
uncommitted full-corpus size harness the ADR 0002 measurement (#34) needs, since
this repo is code/config only.

``lxml`` is a dev/test-only dependency, so it is imported lazily inside `_parse`
rather than at module load: ``import sndocs.minify_check`` stays cheap and works
on a plain install; only actually *running* the check needs ``lxml``.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sndocs.minify import MINIFY_OPTIONS, minify_html_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from lxml.html import HtmlElement

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITE = REPO_ROOT / ".sndocs" / "site"

_WS_RE = re.compile(r"\s+")

# The five strict checks, plus the parse-failure catch-all. All of them mean the
# minified page diverged beyond inter-element whitespace -> non-zero exit.
DIVERGENCE_KINDS = (
    "tag-structure",
    "text-content",
    "link-attr",
    "inline-svg",
    "pre-text",
    "parse-failure",
)


def _parse(html: str) -> "HtmlElement":
    """Parse a full HTML document with the node-count, tree-depth and
    text-length limits lifted (``huge_tree=True``). The `australia` corpus's
    auto-generated API index pages run past libxml2's defaults — without this
    the *larger* original silently truncates while the smaller minified output
    parses whole, manufacturing a divergence that isn't there. A fresh parser
    per call keeps its error log from leaking between pages.

    ``recover=True`` (libxml2's default) is required — real corpus HTML is full
    of recoverable slips — and does not hide re-parenting bugs: the repaired
    tree still has the wrong nesting, which `_skeleton` compares."""
    import lxml.html

    parser = lxml.html.HTMLParser(huge_tree=True, recover=True)
    return lxml.html.document_fromstring(html, parser=parser)


def _collapse(text: str | None) -> str:
    """Collapse internal whitespace runs to single spaces and strip the ends."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip()


def _skeleton(root: "HtmlElement") -> list[tuple[int, str]]:
    """The tree's shape as a pre-order ``(depth, tag)`` list — which, read in
    document order, pins every element's tag *and* its nesting, so a rename,
    drop, insertion or re-parenting all change it. Built with an explicit stack,
    not recursion, so a pathologically deep page can't blow the stack.

    Attributes are deliberately absent: the conservative profile makes safe
    attribute edits — collapsing a space-separated ``class``, dropping a
    redundant ``type="text"`` — that Material for MkDocs triggers on nearly
    every page and that are not divergences. Comments / PIs (non-string ``tag``)
    are excluded, so stripping them is not a divergence either. ``href`` /
    ``src`` values get their own byte-exact check in `_link_attrs`."""
    out: list[tuple[int, str]] = []
    stack: list[tuple[HtmlElement, int]] = [(root, 0)]
    while stack:
        el, depth = stack.pop()
        if not isinstance(el.tag, str):
            continue
        out.append((depth, el.tag))
        stack.extend((child, depth + 1) for child in reversed(el))
    return out


def _text_tokens(root: "HtmlElement") -> list[str]:
    """Every non-empty text node in document order, internal whitespace
    collapsed. Iterating *all* nodes (comments included) keeps a comment's tail
    text attached where a bare element walk would drop it. A purely-whitespace
    node collapses to ``""`` and is omitted from both sides, so inter-element
    whitespace never registers as a difference."""
    tokens: list[str] = []
    for node in root.iter():
        if isinstance(node.tag, str):
            head = _collapse(node.text)
            if head:
                tokens.append(head)
        tail = _collapse(node.tail)
        if tail:
            tokens.append(tail)
    return tokens


def _link_attrs(root: "HtmlElement") -> list[tuple[str, str]]:
    """Every ``href`` / ``src`` attribute value in document order, exactly as
    parsed (``lxml`` does not decode a semicolon-less ``&sect`` prefix, so a
    minifier that *did* decode one shows up as a mismatched value here)."""
    out: list[tuple[str, str]] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for name in ("href", "src"):
            value = el.get(name)
            if value is not None:
                out.append((name, value))
    return out


def _structure(el: "HtmlElement") -> tuple:
    """A hashable (tag, sorted-attrs, child-structures) snapshot of a subtree —
    attributes included, unlike `_skeleton`."""
    return (
        el.tag,
        tuple(sorted(el.attrib.items())),
        tuple(_structure(child) for child in el if isinstance(child.tag, str)),
    )


def _svg_structures(root: "HtmlElement") -> list[tuple]:
    return [_structure(el) for el in root.iter() if el.tag == "svg"]


def _pre_texts(root: "HtmlElement") -> list[str]:
    """Entity-decoded text of every ``<pre>`` block, whitespace untouched."""
    return [el.text_content() for el in root.iter() if el.tag == "pre"]


@dataclass
class Divergence:
    """One way a minified page diverges from its original beyond inter-element
    whitespace."""

    path: str
    kind: str
    detail: str


# Each check: (kind, extractor, human detail). The extractor pulls one
# comparable value out of a parsed tree; the pair diverges on that check when
# the original's value != the minified's. All five mean a divergence beyond
# inter-element whitespace -> non-zero exit; `parse-failure` is handled ahead of
# the table.
_CHECKS: tuple[tuple[str, "Callable[[HtmlElement], object]", str], ...] = (
    ("tag-structure", _skeleton, "the element tree changed (rename, drop, insertion or re-parenting)"),
    ("text-content", _text_tokens, "a non-whitespace text node changed, moved, or was dropped"),
    ("link-attr", _link_attrs, "an href/src attribute value changed"),
    ("inline-svg", _svg_structures, "an inline <svg> subtree changed shape"),
    ("pre-text", _pre_texts, "a <pre> block's text changed after entity-decoding (whitespace loss)"),
)


def compare_html(path: str, original: str, minified: str) -> list[Divergence]:
    """Run all five checks (plus parse-failure) on one original/minified pair."""
    try:
        original_tree = _parse(original)
    except Exception as exc:  # pragma: no cover - MkDocs output always parses
        return [Divergence(path, "parse-failure", f"original did not parse: {exc}")]
    try:
        minified_tree = _parse(minified)
    except Exception as exc:
        return [Divergence(path, "parse-failure", f"minified did not parse: {exc}")]

    findings: list[Divergence] = []
    for kind, extract, detail in _CHECKS:
        before, after = extract(original_tree), extract(minified_tree)
        if before != after:
            findings.append(Divergence(path, kind, detail + _first_diff(before, after)))
    return findings


def _first_diff(before: object, after: object) -> str:
    """A short `; first change: <x> -> <y>` note for the first differing element
    of two lists, truncated. Empty string when the two aren't both lists (a
    nested `_skeleton` tuple would repr huge) or differ only in length."""
    if not isinstance(before, list) or not isinstance(after, list):
        return ""
    for a, b in zip(before, after):
        if a != b:
            return f"; first change: {a!r:.120} -> {b!r:.120}"
    return ""


@dataclass
class PageResult:
    path: str
    bytes_before: int
    bytes_after: int
    divergences: list[Divergence]


@dataclass
class CheckReport:
    pages: list[PageResult] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return len(self.pages)

    @property
    def divergences(self) -> list[Divergence]:
        return [d for page in self.pages for d in page.divergences]

    @property
    def clean(self) -> bool:
        return not self.divergences

    @property
    def bytes_before(self) -> int:
        return sum(page.bytes_before for page in self.pages)

    @property
    def bytes_after(self) -> int:
        return sum(page.bytes_after for page in self.pages)

    @property
    def percent_reduction(self) -> float:
        if not self.bytes_before:
            return 0.0
        return 100.0 * (self.bytes_before - self.bytes_after) / self.bytes_before

    def summary(self) -> str:
        by_kind: dict[str, list[str]] = {}
        for divergence in self.divergences:
            by_kind.setdefault(divergence.kind, []).append(divergence.path)
        lines = [
            f"checked {self.checked} page(s) against the {len(MINIFY_OPTIONS)}-option "
            f"conservative profile; {len(self.divergences)} divergence(s)"
        ]
        for kind in DIVERGENCE_KINDS:
            paths = by_kind.get(kind)
            if not paths:
                continue
            example = paths[0]
            more = f" (+{len(paths) - 1} more)" if len(paths) > 1 else ""
            lines.append(f"  {len(paths):5d}  {kind}  e.g. {example}{more}")
        lines.append(
            f"aggregate: {self.bytes_before} -> {self.bytes_after} bytes "
            f"({self.percent_reduction:.1f}% reduction over {self.checked} page(s))"
        )
        return "\n".join(lines)


def check_pages(paths: list[Path], site_root: Path) -> CheckReport:
    """Minify and compare every page in `paths` (each relative to `site_root`)."""
    report = CheckReport()
    for relative in paths:
        posix = relative.as_posix()
        raw = (site_root / relative).read_bytes()
        original = raw.decode("utf-8")
        minified = minify_html_text(original)
        report.pages.append(
            PageResult(
                path=posix,
                bytes_before=len(raw),
                bytes_after=len(minified.encode("utf-8")),
                divergences=compare_html(posix, original, minified),
            )
        )
    return report


def _discover(site_root: Path) -> list[Path]:
    return sorted(
        (
            p.relative_to(site_root)
            for p in site_root.rglob("*.html")
            if p.is_file()
        ),
        key=lambda p: p.as_posix(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--site",
        type=Path,
        default=DEFAULT_SITE,
        help="Built site root (default: .sndocs/site).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Check a random sample of N pages instead of all.",
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="Random seed for --sample (default: 0)."
    )
    parser.add_argument(
        "--show",
        type=int,
        default=20,
        help="Max divergences to print in detail (default: 20).",
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, help="Explicit site-relative page paths to check."
    )
    args = parser.parse_args(argv)

    if not args.site.is_dir():
        parser.error(
            f"built site does not exist: {args.site} (run `sndocs build --minify` first)"
        )

    if args.paths:
        paths = list(args.paths)
        missing = [p for p in paths if not (args.site / p).is_file()]
        if missing:
            parser.error(
                f"not found under {args.site}: {', '.join(str(p) for p in missing)}"
            )
    else:
        paths = _discover(args.site)
        if not paths:
            parser.error(f"no .html pages under {args.site}")
        if args.sample is not None:
            paths = random.Random(args.seed).sample(paths, min(args.sample, len(paths)))
            paths.sort(key=lambda p: p.as_posix())

    report = check_pages(paths, args.site)
    print(report.summary())
    for divergence in report.divergences[: args.show]:
        print(f"\n{divergence.path}\n  {divergence.kind}: {divergence.detail}")
    return 1 if report.divergences else 0


if __name__ == "__main__":
    sys.exit(main())
