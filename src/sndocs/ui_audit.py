from __future__ import annotations

import html
import json
import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

from markdown import markdown

from . import __version__
from .quality import QualityRuleset, load_quality_ruleset

MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]{1,200}\]\([^) \n]+(?:\s+[^)\n]+)?\)")
ESCAPED_TEXT_RE = re.compile(r"\\[()[\]_*]")
RAW_MARKDOWN_HREF_RE = re.compile(r"(?:^|/)[^?#]+\.md(?:[?#]|$)", re.IGNORECASE)
AUDIT_SECTION_RE = re.compile(
    r"<(?P<tag>table|nav)\b[^>]*>.*?</(?P=tag)\s*>", re.IGNORECASE | re.DOTALL
)
ANCHOR_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a\s*>", re.IGNORECASE | re.DOTALL
)
HREF_RE = re.compile(
    r"\bhref\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
NON_PROSE_RE = re.compile(
    r"<(?:pre|code|script|style)\b[^>]*>.*?</(?:pre|code|script|style)\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _audit_paths_overlap(site: Path, output: Path) -> bool:
    """Return whether an audit report path could modify its input site."""
    resolved_site = site.resolve()
    resolved_output = output.resolve()
    return (
        resolved_site == resolved_output
        or resolved_output.is_relative_to(resolved_site)
        or resolved_site.is_relative_to(resolved_output)
    )


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _page_url(path: Path, site: Path) -> str:
    relative = path.relative_to(site).as_posix()
    if relative == "index.html":
        return "/"
    if relative.endswith("/index.html"):
        return "/" + relative.removesuffix("index.html")
    return "/" + relative


def _local_target_url(page_url: str, href: str) -> str | None:
    parsed = urlsplit(html.unescape(href))
    if parsed.scheme or parsed.netloc or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    raw_path = unquote(parsed.path)
    target = urlsplit(urljoin(page_url, raw_path)).path
    target = "/" + posixpath.normpath(target).lstrip("/")
    if not raw_path or raw_path.endswith("/") or PurePosixPath(target).suffix == "":
        target = target.rstrip("/") + "/index.html"
    return target


@dataclass
class Observation:
    detector_id: str
    confidence: str
    message: str
    context: str
    representative_url: str
    affected_pages: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "detector_id": self.detector_id,
            "confidence": self.confidence,
            "message": self.message,
            "context": self.context,
            "representative_url": self.representative_url,
            "affected_page_count": len(self.affected_pages),
        }


class FindingStore:
    def __init__(self, ruleset: QualityRuleset) -> None:
        self.ruleset = ruleset
        self._observations: dict[tuple[str, str, str], Observation] = {}

    def add(
        self,
        detector_id: str,
        message: str,
        context: str,
        page_url: str,
        *,
        fingerprint: str | None = None,
    ) -> Observation:
        detector = self.ruleset.detectors.get(detector_id)
        if detector is None:
            raise ValueError(f"unknown quality detector: {detector_id}")
        normalized = _normalized_text(context)[:500]
        key = (detector_id, fingerprint or normalized, message)
        observation = self._observations.get(key)
        if observation is None:
            observation = Observation(
                detector_id,
                detector.confidence,
                message,
                normalized,
                page_url,
            )
            self._observations[key] = observation
        observation.affected_pages.add(page_url)
        return observation

    def findings(self) -> list[dict]:
        severity_order = {"error": 0, "warning": 1, "info": 2}
        grouped: dict[str, list[Observation]] = defaultdict(list)
        for observation in self._observations.values():
            detector = self.ruleset.detectors[observation.detector_id]
            grouped[detector.rule_id].append(observation)
        results: list[dict] = []
        for rule_id, observations in grouped.items():
            rule = self.ruleset.rules[rule_id]
            ordered = sorted(
                observations,
                key=lambda item: (
                    item.detector_id,
                    item.representative_url,
                    item.context,
                ),
            )
            affected = set().union(*(item.affected_pages for item in ordered))
            results.append(
                {
                    "rule_id": rule.id,
                    "title": rule.title,
                    "severity": rule.severity,
                    "assessment": rule.assessment,
                    "affected_page_count": len(affected),
                    "observations": [item.to_dict() for item in ordered],
                }
            )
        return sorted(
            results,
            key=lambda item: (
                severity_order.get(item["severity"], 9),
                item["rule_id"],
            ),
        )


@dataclass
class StaticAudit:
    pages: list[str]


def structural_audit(site: Path, findings: FindingStore) -> StaticAudit:
    pages: list[str] = []
    all_files = {
        "/" + path.relative_to(site).as_posix()
        for path in site.rglob("*")
        if path.is_file()
    }
    html_pages = sorted(path for path in site.rglob("*.html"))
    for page in html_pages:
        page_url = _page_url(page, site)
        pages.append(page_url)
        source = page.read_text(encoding="utf-8", errors="replace")
        sections = list(AUDIT_SECTION_RE.finditer(source))
        for section in sections:
            section_source = section.group(0)
            prose_source = NON_PROSE_RE.sub(" ", section_source)
            visible = _normalized_text(html.unescape(TAG_RE.sub(" ", prose_source)))
            markdown_matches = MARKDOWN_LINK_RE.findall(visible)
            for markdown_match in markdown_matches:
                findings.add(
                    "static.visible-markdown-link",
                    "Markdown link syntax is visible in rendered text.",
                    markdown_match,
                    page_url,
                    fingerprint=f"{section.group('tag').casefold()}-markdown-link",
                )
            if (
                section.group("tag").casefold() == "nav"
                and ESCAPED_TEXT_RE.search(visible)
            ):
                for escaped_match in ESCAPED_TEXT_RE.findall(visible):
                    findings.add(
                        "static.visible-markdown-escape",
                        "Markdown escape syntax is visible in navigation or link text.",
                        escaped_match,
                        page_url,
                    )
            if section.group("tag").casefold() == "nav":
                counts: dict[tuple[str, str], int] = defaultdict(int)
                for anchor in ANCHOR_RE.finditer(section_source):
                    href_match = HREF_RE.search(anchor.group("attrs"))
                    if not href_match:
                        continue
                    href = next(value for value in href_match.groups() if value is not None)
                    label = _normalized_text(
                        html.unescape(TAG_RE.sub(" ", anchor.group("body")))
                    ).casefold()
                    if label:
                        counts[(label, href)] += 1
                for (label, href), count in counts.items():
                    if count > 1:
                        findings.add(
                            "static.duplicate-navigation-entry",
                            "The rendered navigation repeats the same label and destination.",
                            f"{label} -> {href}",
                            page_url,
                        )
        for anchor in ANCHOR_RE.finditer(source):
            href_match = HREF_RE.search(anchor.group("attrs"))
            if not href_match:
                continue
            href = next(value for value in href_match.groups() if value is not None)
            label = _normalized_text(
                html.unescape(TAG_RE.sub(" ", anchor.group("body")))
            )
            parsed_href = urlsplit(html.unescape(href))
            is_local = not parsed_href.scheme and not parsed_href.netloc
            if is_local and RAW_MARKDOWN_HREF_RE.search(href):
                findings.add(
                    "static.raw-markdown-destination",
                    "A generated link still targets a Markdown file.",
                    f"{label} -> {href}",
                    page_url,
                )
            suffix = PurePosixPath(unquote(parsed_href.path)).suffix.casefold()
            checkable_local = (
                is_local
                and "${" not in href
                and suffix not in {".do", ".xml", ".json", ".txt"}
            )
            target = _local_target_url(page_url, href) if checkable_local else None
            if target is not None:
                if target not in all_files:
                    findings.add(
                        "static.missing-local-target",
                        "A same-site link target does not exist.",
                        f"{label} -> {href}",
                        page_url,
                    )
            if MARKDOWN_LINK_RE.search(label):
                findings.add(
                    "static.suspicious-link-label",
                    "A link label contains Markdown link syntax.",
                    label,
                    page_url,
                )
    return StaticAudit(pages)


def _report_html(report: dict, ruleset: QualityRuleset) -> str:
    cards = []
    for finding in report["findings"]:
        observations = []
        for observation in finding["observations"]:
            observations.append(
                f'<section class="observation"><h3>{html.escape(observation["detector_id"])}</h3>'
                f'<p><strong>Confidence: {html.escape(observation["confidence"])}</strong>'
                f' · {observation["affected_page_count"]} affected page(s)</p>'
                f'<p>{html.escape(observation["message"])}</p>'
                f'<p><code>{html.escape(observation["representative_url"])}</code></p>'
                f'<pre>{html.escape(observation["context"])}</pre></section>'
            )
        rule = ruleset.rules[finding["rule_id"]]
        cards.append(
            f'<article class="{finding["severity"]}">'
            f'<h2>{html.escape(finding["rule_id"])} — {html.escape(finding["title"])}</h2>'
            f'<p><strong>{html.escape(finding["severity"].upper())}</strong> · '
            f'{finding["affected_page_count"]} affected page(s)</p>'
            f'<p>{html.escape(rule.sections["Requirement"])}</p>'
            f'{"".join(observations)}'
            f'<details><summary>Rule definition</summary>{markdown(rule.body)}</details></article>'
        )
    unevaluated = [
        rule
        for rule in sorted(ruleset.rules.values(), key=lambda item: item.id)
        if rule.status == "active" and rule.assessment != "automated"
    ]
    unevaluated_html = "".join(
        f"<li><strong>{html.escape(rule.id)}</strong> — {html.escape(rule.title)} "
        f"({html.escape(rule.assessment)})</li>"
        for rule in unevaluated
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sndocs UI audit</title>
<style>
body{{font:16px/1.5 system-ui;max-width:78rem;margin:auto;padding:2rem;background:#faf7f2;color:#262626}}
header,article{{background:white;border:1px solid #ddd;border-radius:.4rem;padding:1rem 1.25rem;margin:1rem 0}}
article.error{{border-left:.35rem solid #d7263d}}article.warning{{border-left:.35rem solid #ff8c42}}
.observation{{border-top:1px solid #ddd;margin-top:1rem;padding-top:.5rem}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f1ed;padding:.75rem}}a{{color:#6a4cff}}
</style>
<header><h1>sndocs UI audit</h1>
<p>{report["coverage"]["html_pages"]} HTML pages scanned; {len(report["findings"])} rule finding(s).</p>
<p>Ruleset <code>{html.escape(report["ruleset"]["digest"])}</code></p>
</header>
<section>{"".join(cards) or "<p>No findings.</p>"}</section>
<section><h2>Active rules not automatically evaluated</h2><ul>{unevaluated_html or "<li>None</li>"}</ul></section>
"""


def audit_site_ui(site: Path, output: Path) -> dict:
    """Scan every generated HTML page with the static detectors.

    This is a structural audit only: it reads the assembled site and writes a
    separate report, but never renders a browser. Findings never fail the
    command. See ADR-0024 for why browser-based checks were withdrawn and what
    replaces their coverage.
    """
    if _audit_paths_overlap(site, output):
        raise ValueError(f"audit output must not overlap input site: {output}")
    manifest_path = site / "build-manifest.json"
    if not site.is_dir() or not manifest_path.is_file():
        raise ValueError(f"site has no build-manifest.json: {site}")
    json.loads(manifest_path.read_text(encoding="utf-8"))
    ruleset = load_quality_ruleset()
    findings = FindingStore(ruleset)
    static = structural_audit(site, findings)
    output.mkdir(parents=True)
    report = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": str(site),
        "ruleset": {
            "schema_version": ruleset.schema_version,
            "package_version": __version__,
            "name": ruleset.name,
            "digest": ruleset.digest,
            "rules": ruleset.catalog(active_only=True),
        },
        "coverage": {
            "html_pages": len(static.pages),
        },
        "findings": findings.findings(),
    }
    (output / "findings.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "index.html").write_text(_report_html(report, ruleset), encoding="utf-8")
    return report
