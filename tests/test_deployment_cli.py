from __future__ import annotations

import json
from pathlib import Path

import pytest

from sndocs.deployment_cli import main

CONFIG = Path(__file__).parents[1] / "pipeline.toml"


def _discovery(tmp_path: Path) -> Path:
    path = tmp_path / "discovery.json"
    path.write_text(
        json.dumps({"latest": "yokohama", "shas": {"yokohama": "sha-1"}}),
        encoding="utf-8",
    )
    return path


def test_plan_rejects_a_missing_active_release_file(tmp_path, capsys):
    discovery = _discovery(tmp_path)

    status = main(
        [
            "plan",
            "--config",
            str(CONFIG),
            "--discovery",
            str(discovery),
            "--active-release",
            str(tmp_path / "absent.json"),
            "--output",
            str(tmp_path / "plan.json"),
        ]
    )

    assert status == 2
    assert "required input is missing" in capsys.readouterr().err
    assert not (tmp_path / "plan.json").exists()


def test_plan_requires_an_explicit_active_release_decision(tmp_path):
    discovery = _discovery(tmp_path)

    with pytest.raises(SystemExit) as error:
        main(
            [
                "plan",
                "--config",
                str(CONFIG),
                "--discovery",
                str(discovery),
                "--output",
                str(tmp_path / "plan.json"),
            ]
        )

    assert error.value.code == 2


def test_plan_without_an_active_release_is_an_initial_release(tmp_path):
    discovery = _discovery(tmp_path)
    output = tmp_path / "plan.json"

    status = main(
        [
            "plan",
            "--config",
            str(CONFIG),
            "--discovery",
            str(discovery),
            "--no-active-release",
            "--output",
            str(output),
        ]
    )

    assert status == 0
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan["action"] == "initial"
    assert plan["latest"] == "yokohama"


def test_assemble_requires_an_explicit_active_release_decision(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(
            [
                "assemble",
                "--site",
                str(tmp_path / "site"),
                "--inventory",
                str(tmp_path / "inventory.json"),
                "--output-root",
                str(tmp_path / "root"),
                "--output-manifest",
                str(tmp_path / "manifest.json"),
            ]
        )

    assert error.value.code == 2
