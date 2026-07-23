from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from importlib import resources
from pathlib import Path

import pytest
import yaml

from sndocs.quality import DEFAULT_DETECTORS, Detector, load_quality_ruleset
from sndocs.ui_audit import _report_html


def _copy_ruleset(tmp_path: Path) -> Path:
    source = Path(str(resources.files("sndocs.quality_rules")))
    target = tmp_path / "quality_rules"
    shutil.copytree(source, target)
    return target


def _add_rule(root: Path, rule_id: str, *, status: str, assessment: str) -> Path:
    source = root / "rules" / "SND-FUNC-001-no-page-errors.md"
    text = source.read_text(encoding="utf-8")
    text = text.replace("SND-FUNC-001", rule_id)
    text = text.replace("status: active", f"status: {status}")
    text = text.replace("assessment: automated", f"assessment: {assessment}")
    target = root / "rules" / f"{rule_id}-fixture-rule.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_packaged_ruleset_loads_and_has_deterministic_digest(tmp_path):
    packaged = load_quality_ruleset()
    copied_root = _copy_ruleset(tmp_path)
    copied = load_quality_ruleset(copied_root)

    assert len(packaged.rules) == 10
    assert len(packaged.detectors) == 14
    assert packaged.digest == copied.digest
    assert [item["id"] for item in packaged.catalog()] == sorted(packaged.rules)

    target = copied_root / "rules" / "SND-NAV-001-duplicate-navigation-entries.md"
    text = target.read_text(encoding="utf-8")
    marker = text.index("\n---\n", 4)
    metadata = yaml.safe_load(text[4:marker])
    reordered = "---\n" + yaml.safe_dump(metadata, sort_keys=True) + "---\n" + text[marker + 5 :]
    target.write_bytes(reordered.replace("\n", "\r\n").encode())
    assert load_quality_ruleset(copied_root).digest == packaged.digest


def test_draft_manual_and_assisted_rules_do_not_require_detectors(tmp_path):
    root = _copy_ruleset(tmp_path)
    _add_rule(root, "SND-TEST-901", status="draft", assessment="automated")
    _add_rule(root, "SND-TEST-902", status="active", assessment="manual")
    _add_rule(root, "SND-TEST-903", status="active", assessment="assisted")
    _add_rule(root, "SND-TEST-905", status="deprecated", assessment="manual")
    _add_rule(root, "SND-TEST-906", status="retired", assessment="manual")

    ruleset = load_quality_ruleset(root)

    assert ruleset.rules["SND-TEST-901"].status == "draft"
    assert ruleset.rules["SND-TEST-902"].assessment == "manual"
    assert ruleset.rules["SND-TEST-903"].assessment == "assisted"
    catalog = {item["id"]: item for item in ruleset.catalog()}
    assert catalog["SND-TEST-902"]["assessment"] == "manual"
    assert catalog["SND-TEST-903"]["assessment"] == "assisted"
    active_ids = {item["id"] for item in ruleset.catalog(active_only=True)}
    assert "SND-TEST-905" not in active_ids
    assert "SND-TEST-906" not in active_ids

    report = {
        "findings": [],
        "errors": [],
        "coverage": {"html_pages": 0, "browser_renders": 0},
        "ruleset": {"digest": ruleset.digest},
    }
    rendered = _report_html(report, ruleset)
    assert "SND-TEST-902" in rendered and "(manual)" in rendered
    assert "SND-TEST-903" in rendered and "(assisted)" in rendered
    assert "SND-TEST-905" not in rendered and "SND-TEST-906" not in rendered


def test_active_automated_rule_requires_detector(tmp_path):
    root = _copy_ruleset(tmp_path)
    _add_rule(root, "SND-TEST-904", status="active", assessment="automated")

    with pytest.raises(ValueError, match="active automated rule has no detector"):
        load_quality_ruleset(root)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("schema_version: 1", "schema_version: 2", "schema_version must be 1"),
        ("  warning:", "  caution:", "must define error, warning, and info"),
        ("  low:", "  uncertain:", "must define high, medium, and low"),
    ],
)
def test_ruleset_configuration_is_strict(tmp_path, old, new, message):
    root = _copy_ruleset(tmp_path)
    target = root / "ruleset.yml"
    target.write_text(target.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_quality_ruleset(root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda text: text.replace("references: []\n", ""), "missing fields"),
        (lambda text: text.replace("tags:", "unknown: value\ntags:"), "unknown fields"),
        (lambda text: text.replace("severity: warning", "severity: impossible"), "invalid severity"),
        (lambda text: text.replace("## Requirement", "## Different"), "required sections"),
        (
            lambda text: text.replace(
                "Duplicates obscure hierarchy, waste navigation space, and make the generated "
                "information architecture appear unreliable.",
                "",
            ),
            "cannot be empty",
        ),
    ],
)
def test_invalid_rule_definitions_are_rejected(tmp_path, mutation, message):
    root = _copy_ruleset(tmp_path)
    target = root / "rules" / "SND-NAV-001-duplicate-navigation-entries.md"
    target.write_text(mutation(target.read_text(encoding="utf-8")), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_quality_ruleset(root)


def test_filename_mismatch_and_duplicate_ids_are_rejected(tmp_path):
    root = _copy_ruleset(tmp_path)
    original = root / "rules" / "SND-NAV-001-duplicate-navigation-entries.md"
    mismatch = root / "rules" / "SND-NAV-999-wrong.md"
    original.rename(mismatch)
    with pytest.raises(ValueError, match="filename must begin"):
        load_quality_ruleset(root)

    mismatch.rename(original)
    duplicate = root / "rules" / "SND-NAV-001-second-definition.md"
    shutil.copy2(original, duplicate)
    with pytest.raises(ValueError, match="duplicate quality rule id"):
        load_quality_ruleset(root)


@pytest.mark.parametrize(
    ("detector", "message"),
    [
        (Detector("fixture.unknown", "SND-NOPE-999", "static", "high"), "unknown quality rule"),
        (Detector("fixture.phase", "SND-NAV-001", "invalid", "high"), "invalid detector phase"),
        (Detector("fixture.confidence", "SND-NAV-001", "static", "certain"), "invalid detector confidence"),
    ],
)
def test_invalid_detector_registration_is_rejected(tmp_path, detector, message):
    root = _copy_ruleset(tmp_path)
    with pytest.raises(ValueError, match=message):
        load_quality_ruleset(root, detectors=(*DEFAULT_DETECTORS, detector))


def test_duplicate_and_retired_detector_registration_is_rejected(tmp_path):
    root = _copy_ruleset(tmp_path)
    duplicate = Detector(
        DEFAULT_DETECTORS[0].id, "SND-RENDER-001", "static", "high"
    )
    with pytest.raises(ValueError, match="duplicate quality detector"):
        load_quality_ruleset(root, detectors=(*DEFAULT_DETECTORS, duplicate))

    target = root / "rules" / "SND-NAV-001-duplicate-navigation-entries.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("status: active", "status: retired"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="is not active"):
        load_quality_ruleset(root)


def test_quality_cli_validate_list_show_and_errors(tmp_path):
    command = [sys.executable, "-m", "sndocs.cli", "quality"]

    validated = subprocess.run(
        [*command, "validate", "--json"], check=True, capture_output=True, text=True, cwd=tmp_path
    )
    assert json.loads(validated.stdout)["rules"] == 10

    listed = subprocess.run(
        [*command, "list", "--category", "navigation", "--status", "active", "--json"],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert [item["id"] for item in json.loads(listed.stdout)["rules"]] == ["SND-NAV-001"]

    shown = subprocess.run(
        [*command, "show", "SND-NAV-001"], check=True, capture_output=True, text=True, cwd=tmp_path
    )
    assert shown.stdout.startswith("---\nid: SND-NAV-001")
    shown_json = subprocess.run(
        [*command, "show", "SND-NAV-001", "--json"],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert json.loads(shown_json.stdout)["sections"]["Requirement"]

    unknown = subprocess.run(
        [*command, "show", "SND-NAV-999"], check=False, capture_output=True, text=True, cwd=tmp_path
    )
    assert unknown.returncode == 2
    assert "unknown quality rule" in unknown.stderr


def test_wheel_contains_complete_quality_ruleset(tmp_path):
    root = Path(__file__).parents[1]
    destination = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
    )
    wheel = next(destination.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert "sndocs/quality_rules/ruleset.yml" in names
    assert "sndocs/quality_rules/README.md" in names
    packaged_rules = {
        name for name in names if name.startswith("sndocs/quality_rules/rules/") and name.endswith(".md")
    }
    expected_rules = {
        f"sndocs/quality_rules/rules/{rule.filename}"
        for rule in load_quality_ruleset().rules.values()
    }
    assert packaged_rules == expected_rules
