import json

from sndocs import builder
from sndocs.models import Discovery, Settings


def settings(root):
    return Settings(root, "site", "", "", "owner/repo", "llms.txt", (), "site")


def test_plan_reports_reuse_rebuild_and_stable_archive(tmp_path, monkeypatch):
    previous = tmp_path / "previous"
    (previous / "australia").mkdir(parents=True)
    (previous / "zurich").mkdir()
    (previous / "build-manifest.json").write_text(json.dumps({
        "pipeline_fingerprint": "same",
        "build_profile": "production",
        "latest": "australia",
        "families": {
            "australia": {"source_sha": "one", "archived": False},
            "zurich": {"source_sha": "old", "archived": True},
        },
    }), encoding="utf-8")
    monkeypatch.setattr(builder, "pipeline_fingerprint", lambda _root: "same")
    discovery = Discovery(["australia"], "australia", [], {"australia": "one"})

    plan = builder.plan_build(settings(tmp_path), previous, discovery)

    assert [(item["family"], item["action"]) for item in plan["actions"]] == [
        ("australia", "reuse"), ("zurich", "archive")
    ]
    assert plan["changed"] is False


def test_plan_rebuild_reasons_cover_sha_profile_and_missing_output(tmp_path, monkeypatch):
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "build-manifest.json").write_text(json.dumps({
        "pipeline_fingerprint": "same",
        "build_profile": "production",
        "latest": "australia",
        "families": {"australia": {"source_sha": "old", "archived": False}},
    }), encoding="utf-8")
    monkeypatch.setattr(builder, "pipeline_fingerprint", lambda _root: "same")
    discovery = Discovery(["australia"], "australia", [], {"australia": "new"})

    assert builder.plan_build(settings(tmp_path), previous, discovery)["actions"][0]["reason"] == "source SHA changed"
    missing = Discovery(["australia"], "australia", [], {"australia": "old"})
    assert builder.plan_build(settings(tmp_path), previous, missing)["actions"][0]["reason"] == "reusable family output is missing"
    assert builder.plan_build(settings(tmp_path), previous, missing, build_profile="smoke")["actions"][0]["reason"] == "build profile changed"
