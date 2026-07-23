from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable

import yaml

RULE_ID_RE = re.compile(r"^SND-[A-Z]+-\d{3}$")
REQUIRED_FIELDS = {
    "id",
    "title",
    "status",
    "category",
    "severity",
    "assessment",
    "references",
    "tags",
}
REQUIRED_SECTIONS = (
    "Requirement",
    "Rationale",
    "Applicability",
    "Passing Examples",
    "Failing Examples",
    "Evaluation",
    "Limitations",
    "Remediation",
    "References",
)
STATUSES = {"draft", "active", "deprecated", "retired"}
ASSESSMENTS = {"automated", "assisted", "manual"}
PHASES = {"static", "browser"}
CONFIDENCE = {"high", "medium", "low"}


@dataclass(frozen=True)
class QualityRule:
    id: str
    title: str
    status: str
    category: str
    severity: str
    assessment: str
    references: tuple[dict | str, ...]
    tags: tuple[str, ...]
    body: str
    sections: dict[str, str]
    filename: str
    source: str

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "category": self.category,
            "severity": self.severity,
            "assessment": self.assessment,
            "references": list(self.references),
            "tags": list(self.tags),
            "requirement": self.sections["Requirement"],
        }

    def to_dict(self, *, include_body: bool = False) -> dict:
        result = self.summary()
        if include_body:
            result["body"] = self.body
            result["sections"] = self.sections
            result["source"] = self.source
        return result


@dataclass(frozen=True)
class Detector:
    id: str
    rule_id: str
    phase: str
    confidence: str


@dataclass(frozen=True)
class QualityRuleset:
    schema_version: int
    name: str
    categories: tuple[str, ...]
    severities: dict[str, str]
    confidence: dict[str, str]
    rules: dict[str, QualityRule]
    detectors: dict[str, Detector]
    digest: str

    def catalog(self, *, active_only: bool = False) -> list[dict]:
        return [
            rule.summary()
            for rule in sorted(self.rules.values(), key=lambda item: item.id)
            if not active_only or rule.status == "active"
        ]


DEFAULT_DETECTORS = (
    Detector("static.visible-markdown-link", "SND-RENDER-001", "static", "high"),
    Detector("static.suspicious-link-label", "SND-RENDER-001", "static", "medium"),
    Detector("browser.visible-markdown-link", "SND-RENDER-001", "browser", "high"),
    Detector("static.visible-markdown-escape", "SND-RENDER-002", "static", "medium"),
    Detector("browser.visible-markdown-escape", "SND-RENDER-002", "browser", "medium"),
    Detector("static.duplicate-navigation-entry", "SND-NAV-001", "static", "medium"),
    Detector("browser.duplicate-navigation-entry", "SND-NAV-001", "browser", "high"),
    Detector("static.raw-markdown-destination", "SND-LINK-001", "static", "high"),
    Detector("static.missing-local-target", "SND-LINK-002", "static", "high"),
    Detector("browser.horizontal-page-overflow", "SND-LAYOUT-001", "browser", "high"),
    Detector("browser.clipped-content", "SND-LAYOUT-002", "browser", "medium"),
    Detector("browser.page-error", "SND-FUNC-001", "browser", "high"),
    Detector("browser.console-error", "SND-FUNC-002", "browser", "medium"),
    Detector("browser.failed-resource", "SND-LINK-003", "browser", "high"),
)


def _read(resource) -> str:
    return resource.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _frontmatter(text: str, filename: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError(f"{filename}: rule must begin with YAML frontmatter")
    marker = text.find("\n---\n", 4)
    if marker < 0:
        raise ValueError(f"{filename}: unterminated YAML frontmatter")
    try:
        metadata = yaml.safe_load(text[4:marker])
    except yaml.YAMLError as error:
        raise ValueError(f"{filename}: invalid YAML frontmatter: {error}") from error
    if not isinstance(metadata, dict):
        raise ValueError(f"{filename}: frontmatter must be a mapping")
    unknown = set(metadata) - REQUIRED_FIELDS
    missing = REQUIRED_FIELDS - set(metadata)
    if missing:
        raise ValueError(f"{filename}: missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{filename}: unknown fields: {', '.join(sorted(unknown))}")
    return metadata, text[marker + 5 :].strip() + "\n"


def _sections(body: str, filename: str, title: str) -> dict[str, str]:
    lines = body.splitlines()
    if not lines or lines[0] != f"# {title}":
        raise ValueError(f"{filename}: first heading must be '# {title}'")
    headings: list[tuple[int, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
            continue
        if fence is None and line.startswith("## "):
            headings.append((index, line[3:].strip()))
    names = [name for _, name in headings]
    if names != list(REQUIRED_SECTIONS):
        raise ValueError(
            f"{filename}: required sections must appear once and in order: "
            + ", ".join(REQUIRED_SECTIONS)
        )
    result: dict[str, str] = {}
    for position, (line_index, name) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        value = "\n".join(lines[line_index + 1 : end]).strip()
        if not value:
            raise ValueError(f"{filename}: section '{name}' cannot be empty")
        result[name] = value
    return result


def _rule(resource, categories: set[str], severities: set[str]) -> QualityRule:
    filename = resource.name
    text = _read(resource)
    metadata, body = _frontmatter(text, filename)
    rule_id = metadata["id"]
    title = metadata["title"]
    if not isinstance(rule_id, str) or not RULE_ID_RE.fullmatch(rule_id):
        raise ValueError(f"{filename}: invalid rule id: {rule_id!r}")
    if not filename.startswith(rule_id + "-"):
        raise ValueError(f"{filename}: filename must begin with {rule_id}-")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{filename}: title must be a nonempty string")
    for field, allowed in (
        ("status", STATUSES),
        ("category", categories),
        ("severity", severities),
        ("assessment", ASSESSMENTS),
    ):
        if not isinstance(metadata[field], str) or metadata[field] not in allowed:
            raise ValueError(f"{filename}: invalid {field}: {metadata[field]!r}")
    references = metadata["references"]
    tags = metadata["tags"]
    if not isinstance(references, list) or not all(
        isinstance(item, (dict, str)) for item in references
    ):
        raise ValueError(f"{filename}: references must be a list of mappings or strings")
    if (
        not isinstance(tags, list)
        or not all(isinstance(item, str) and item for item in tags)
        or len(tags) != len(set(tags))
    ):
        raise ValueError(f"{filename}: tags must be a list of nonempty strings")
    return QualityRule(
        id=rule_id,
        title=title.strip(),
        status=metadata["status"],
        category=metadata["category"],
        severity=metadata["severity"],
        assessment=metadata["assessment"],
        references=tuple(references),
        tags=tuple(tags),
        body=body,
        sections=_sections(body, filename, title.strip()),
        filename=filename,
        source=text,
    )


def _detector_registry(detectors: Iterable[Detector]) -> dict[str, Detector]:
    result: dict[str, Detector] = {}
    for detector in detectors:
        if detector.id in result:
            raise ValueError(f"duplicate quality detector id: {detector.id}")
        if detector.phase not in PHASES:
            raise ValueError(f"{detector.id}: invalid detector phase: {detector.phase}")
        if detector.confidence not in CONFIDENCE:
            raise ValueError(f"{detector.id}: invalid detector confidence: {detector.confidence}")
        result[detector.id] = detector
    return result


def load_quality_ruleset(
    root: Path | None = None,
    *,
    detectors: Iterable[Detector] = DEFAULT_DETECTORS,
) -> QualityRuleset:
    package_root = resources.files("sndocs.quality_rules") if root is None else root
    config_resource = package_root.joinpath("ruleset.yml")
    config_text = _read(config_resource)
    try:
        config = yaml.safe_load(config_text)
    except yaml.YAMLError as error:
        raise ValueError(f"ruleset.yml: invalid YAML: {error}") from error
    required_config = {"schema_version", "name", "categories", "severities", "confidence"}
    if not isinstance(config, dict) or set(config) != required_config:
        raise ValueError("ruleset.yml must contain exactly: " + ", ".join(sorted(required_config)))
    if config["schema_version"] != 1:
        raise ValueError("ruleset.yml schema_version must be 1")
    if not isinstance(config["name"], str) or not config["name"].strip():
        raise ValueError("ruleset.yml name must be a nonempty string")
    categories = config["categories"]
    severities = config["severities"]
    confidence = config["confidence"]
    if (
        not isinstance(categories, list)
        or not categories
        or not all(isinstance(item, str) and item for item in categories)
        or len(categories) != len(set(categories))
    ):
        raise ValueError("ruleset.yml categories must be a nonempty unique list")
    if (
        not isinstance(severities, dict)
        or set(severities) != {"error", "warning", "info"}
        or not all(
            isinstance(key, str) and key and isinstance(value, str) and value
            for key, value in severities.items()
        )
    ):
        raise ValueError("ruleset.yml severities must define error, warning, and info")
    if not isinstance(confidence, dict) or set(confidence) != CONFIDENCE or not all(
        isinstance(value, str) and value for value in confidence.values()
    ):
        raise ValueError("ruleset.yml confidence must define high, medium, and low")
    rules: dict[str, QualityRule] = {}
    rules_resource = package_root.joinpath("rules")
    for resource in sorted(
        (item for item in rules_resource.iterdir() if item.name.endswith(".md")),
        key=lambda item: item.name,
    ):
        rule = _rule(resource, set(categories), set(severities))
        if rule.id in rules:
            raise ValueError(f"duplicate quality rule id: {rule.id}")
        rules[rule.id] = rule
    if not rules:
        raise ValueError("quality ruleset contains no rule definitions")
    registry = _detector_registry(detectors)
    by_rule: dict[str, list[Detector]] = {}
    for detector in registry.values():
        rule = rules.get(detector.rule_id)
        if rule is None:
            raise ValueError(f"{detector.id}: unknown quality rule: {detector.rule_id}")
        if rule.status != "active":
            raise ValueError(f"{detector.id}: quality rule {rule.id} is not active")
        by_rule.setdefault(rule.id, []).append(detector)
    for rule in rules.values():
        if rule.status == "active" and rule.assessment == "automated" and rule.id not in by_rule:
            raise ValueError(f"{rule.id}: active automated rule has no detector")
        if rule.status == "retired" and rule.id in by_rule:
            raise ValueError(f"{rule.id}: retired rule cannot have detectors")
    normalized = {
        "config": config,
        "rules": [
            {
                "metadata": rule.summary(),
                "body": rule.body,
            }
            for rule in sorted(rules.values(), key=lambda item: item.id)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return QualityRuleset(
        schema_version=1,
        name=config["name"].strip(),
        categories=tuple(categories),
        severities=dict(severities),
        confidence=dict(confidence),
        rules=rules,
        detectors=registry,
        digest=digest,
    )
