from __future__ import annotations

import json
from pathlib import Path

import pytest

from sndocs import cli
from sndocs.models import Discovery


def write_config(root: Path) -> Path:
    path = root / "pipeline.toml"
    path.write_text('[site]\nname = "test"\n[upstream]\nrepository = "owner/repo"\n', encoding="utf-8")
    return path


def result(families: list[str] | None = None) -> Discovery:
    selected = families or ["australia", "zurich"]
    return Discovery(selected, selected[0], [], {family: f"sha-{family}" for family in selected})


def test_common_options_work_before_and_after_commands():
    before = cli.parser().parse_args(["--config", "one.toml", "--json", "discover"])
    after = cli.parser().parse_args(["discover", "--config", "two.toml", "--json"])
    nested = cli.parser().parse_args(["source", "check", "repo", "--config", "three.toml", "--json"])
    assert (before.config, before.json) == (Path("one.toml"), True)
    assert (after.config, after.json) == (Path("two.toml"), True)
    assert (nested.config, nested.json) == (Path("three.toml"), True)


@pytest.mark.parametrize("arguments", [
    ["discover", "--source-repo", "repo"],
    ["discover", "--clone-source", "repo"],
    ["discover", "--refresh-source"],
    ["build", "--previous-site", "site"],
    ["build", "--github-output", "result"],
])
def test_removed_options_are_rejected(arguments):
    with pytest.raises(SystemExit):
        cli.parser().parse_args(arguments)


def test_json_discovery_is_one_clean_object(tmp_path, monkeypatch, capsys):
    config = write_config(tmp_path)
    monkeypatch.setattr(cli, "discover", lambda *_args, **_kwargs: result())
    assert cli.main(["discover", "--config", str(config), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["families"] == ["australia", "zurich"]


def test_existing_output_requires_clean_and_is_not_touched(tmp_path):
    config = write_config(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["build", "--config", str(config), "--output", str(output)])
    assert marker.read_text(encoding="utf-8") == "keep"


def test_clean_happens_only_after_successful_discovery(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(cli, "discover", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad source")))
    with pytest.raises(SystemExit):
        cli.main(["build", "--config", str(config), "--output", str(output), "--clean"])
    assert marker.exists()


def test_clean_replaces_output_after_discovery_succeeds(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "old"
    marker.write_text("old", encoding="utf-8")
    monkeypatch.setattr(cli, "discover", lambda *_args, **_kwargs: result(["australia"]))

    def fake_build(_settings, selected_output, _work, *_args, **_kwargs):
        assert not marker.exists()
        selected_output.mkdir()
        return {"latest": "australia", "families": {"australia": {}}, "build_profile": "production"}, True

    monkeypatch.setattr(cli, "build_site", fake_build)
    assert cli.main(["build", "--config", str(config), "--output", str(output), "--clean"]) == 0
    assert not marker.exists()


def test_dry_run_is_non_mutating_and_does_not_write_github_output(tmp_path, monkeypatch, capsys):
    config = write_config(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("keep", encoding="utf-8")
    github_output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setattr(cli, "discover", lambda *_args, **_kwargs: result(["australia"]))
    assert cli.main(["build", "--config", str(config), "--dry-run", "--output", str(output), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["actions"][0]["action"] == "rebuild"
    assert marker.exists()
    assert not github_output.exists()


def test_build_writes_automatic_github_outputs(tmp_path, monkeypatch, capsys):
    config = write_config(tmp_path)
    output = tmp_path / "site"
    github_output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setattr(cli, "discover", lambda *_args, **_kwargs: result(["australia"]))

    def fake_build(_settings, selected_output, _work, *_args, **_kwargs):
        selected_output.mkdir(parents=True)
        (selected_output / "build-manifest.json").write_text("{}", encoding="utf-8")
        return {"latest": "australia", "families": {"australia": {}}, "build_profile": "production"}, True

    monkeypatch.setattr(cli, "build_site", fake_build)
    assert cli.main(["build", "--config", str(config), "--output", str(output), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["changed"] is True
    assert github_output.read_text(encoding="utf-8") == "changed=true\nlatest=australia\n"


def test_family_validation_rejects_duplicates_and_multiple_smoke_families(tmp_path):
    config = write_config(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["build", "--config", str(config), "--dry-run", "--family", "a", "--family", "a"])
    with pytest.raises(SystemExit):
        cli.main(["build", "--config", str(config), "--dry-run", "--smoke", "--family", "a", "--family", "b"])


def test_validate_json_result(tmp_path, capsys):
    config = write_config(tmp_path)
    site = tmp_path / "site"
    family = site / "australia"
    family.mkdir(parents=True)
    (family / "index.html").write_text("ok", encoding="utf-8")
    (site / "build-manifest.json").write_text(json.dumps({"latest": "australia", "families": {"australia": {}}}), encoding="utf-8")
    (site / "versions.json").write_text(json.dumps({"latest": "australia"}), encoding="utf-8")
    (site / "link-report.json").write_text(json.dumps({
        "schema_version": 2,
        "families": {"australia": {"counts": {
            "document_links": {}, "navigation_links": {}, "placeholders": 0, "omitted_images": {}
        }}},
    }), encoding="utf-8")
    assert cli.main(["validate", "--config", str(config), "--site", str(site), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"site": str(site.resolve()), "valid": True}
