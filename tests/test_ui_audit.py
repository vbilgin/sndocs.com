import json
from pathlib import Path

import pytest

from sndocs import ui_audit
from sndocs.ui_audit import (
    FindingStore,
    StaticAudit,
    audit_site_ui,
    select_pages,
    structural_audit,
)
from sndocs.quality import load_quality_ruleset


def _site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "build-manifest.json").write_text(
        json.dumps({"build_profile": "smoke", "families": {}}), encoding="utf-8"
    )
    return site


def test_structural_audit_detects_and_deduplicates_problem_patterns(tmp_path):
    site = _site(tmp_path)
    for name in ("one", "two"):
        page = site / name
        page.mkdir()
        page.joinpath("index.html").write_text(
            """<nav><ul>
            <li><a href="../target/">Repeated</a></li>
            <li><a href="../target/">Repeated</a></li>
            <li><a href="../missing.md">Service \\(instances\\)</a></li>
            </ul></nav>
            <table><tr><td>[Broken](missing.md)</td></tr></table>""",
            encoding="utf-8",
        )
    target = site / "target"
    target.mkdir()
    target.joinpath("index.html").write_text("<p>ok</p>", encoding="utf-8")
    findings = FindingStore(load_quality_ruleset())

    result = structural_audit(site, findings)
    by_rule = {item["rule_id"]: item for item in findings.findings()}

    assert len(result.pages) == 3
    assert len(result.high_risk_pages) == 1
    assert by_rule["SND-RENDER-001"]["affected_page_count"] == 2
    render_detectors = {
        item["detector_id"] for item in by_rule["SND-RENDER-001"]["observations"]
    }
    assert render_detectors == {"static.visible-markdown-link"}
    assert by_rule["SND-RENDER-001"]["observations"][0]["affected_page_count"] == 2
    assert by_rule["SND-RENDER-002"]["severity"] == "warning"
    assert by_rule["SND-LINK-001"]["severity"] == "error"
    assert by_rule["SND-LINK-002"]["affected_page_count"] == 2
    nav_observation = by_rule["SND-NAV-001"]["observations"][0]
    assert nav_observation["context"] == "repeated -> ../target/"
    assert nav_observation["confidence"] == "medium"


def test_structural_audit_ignores_markdown_syntax_in_code_examples(tmp_path):
    site = _site(tmp_path)
    (site / "index.html").write_text(
        "<table><tr><td><pre><code>[Example](source.md)</code></pre></td></tr></table>",
        encoding="utf-8",
    )
    findings = FindingStore(load_quality_ruleset())
    structural_audit(site, findings)
    assert all(item["rule_id"] != "SND-RENDER-001" for item in findings.findings())


def test_sampling_is_deterministic_and_keeps_high_risk_pages():
    audit = StaticAudit(
        pages=[f"/{number}/" for number in range(10)],
        high_risk_pages={"/9/"},
        table_pages=set(),
        nav_pages=set(),
    )

    first = select_pages(audit, 3, 42)
    second = select_pages(audit, 3, 42)

    assert first == second
    assert "/9/" in first
    assert len(first) == 4
    with pytest.raises(ValueError, match="cannot be negative"):
        select_pages(audit, -1, 0)


def test_audit_is_read_only_and_rejects_overlapping_report_paths(tmp_path, monkeypatch):
    site = _site(tmp_path)
    (site / "index.html").write_text("<p>unchanged</p>", encoding="utf-8")
    before = {
        path.relative_to(site): path.read_bytes()
        for path in site.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(ui_audit, "browser_audit", lambda *_args: 0)

    report = audit_site_ui(site, tmp_path / "report", sample_size=0)

    after = {
        path.relative_to(site): path.read_bytes()
        for path in site.rglob("*")
        if path.is_file()
    }
    assert report["coverage"]["html_pages"] == 1
    assert after == before
    for output in (site, site / "report", tmp_path):
        with pytest.raises(ValueError, match="must not overlap"):
            audit_site_ui(site, output, sample_size=0)
    assert after == {
        path.relative_to(site): path.read_bytes()
        for path in site.rglob("*")
        if path.is_file()
    }


def test_browser_audit_writes_report_and_remains_report_only(tmp_path):
    pytest.importorskip("playwright")
    site = _site(tmp_path)
    (site / "index.html").write_text(
        """<!doctype html><style>
        .wide { width: 900px }
        .intentional-nav-overflow { width: 100px; overflow: hidden }
        .intentional-nav-overflow ul { width: 500px }
        </style><nav><ul>
        <li><a href="/">Duplicate</a></li><li><a href="/">Duplicate</a></li>
        </ul></nav>
        <nav class="intentional-nav-overflow"><ul><li>Sliding Material navigation</li></ul></nav>
        <main><table class="wide"><tr><td>[Visible](missing.md)</td></tr></table></main>""",
        encoding="utf-8",
    )
    output = tmp_path / "report"

    report = audit_site_ui(site, output, sample_size=0, seed=0)

    rules = {item["rule_id"] for item in report["findings"]}
    assert {"SND-RENDER-001", "SND-NAV-001", "SND-LAYOUT-001"} <= rules
    observations = [
        observation
        for finding in report["findings"]
        for observation in finding["observations"]
    ]
    detector_ids = {item["detector_id"] for item in observations}
    assert "static.visible-markdown-link" in detector_ids
    assert "browser.visible-markdown-link" in detector_ids
    assert "browser.horizontal-page-overflow" in detector_ids
    clipped_contexts = {
        item["context"]
        for item in observations
        if item["detector_id"] == "browser.clipped-content"
    }
    assert all('"tag": "nav"' not in context for context in clipped_contexts)
    assert all(item["confidence"] in {"high", "medium", "low"} for item in observations)
    assert report["schema_version"] == 2
    assert report["ruleset"]["schema_version"] == 1
    assert len(report["ruleset"]["digest"]) == 64
    assert len(report["ruleset"]["rules"]) == 10
    assert report["coverage"]["html_pages"] == 1
    assert report["coverage"]["browser_renders"] == 2
    assert (output / "findings.json").is_file()
    assert (output / "index.html").is_file()
    assert list((output / "screenshots").glob("*.png"))
