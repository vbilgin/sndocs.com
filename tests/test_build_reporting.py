import json

from sndocs import builder
from sndocs.models import Discovery, Settings


def settings_for(root):
    return Settings(
        root=root,
        site_name="sndocs.com",
        site_url="https://sndocs.com",
        site_description="Mirror",
        repository="owner/repo",
        llms_path="llms.txt",
        family_allowlist=(),
        archive_basename="sndocs-site",
    )


def test_fresh_build_writes_report_and_manifest_counts(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    discovery = Discovery(["australia"], "australia", [], {"australia": "abc"})
    counts = {"exact": 8, "repaired": 2, "placeholder": 1, "ambiguous": 0}
    report = {
        "family": "australia",
        "counts": counts,
        "repairs": [],
        "placeholders": [],
    }

    monkeypatch.setattr(builder, "discover", lambda _settings: discovery)

    def fake_build(_settings, _discovery, family, _work, output):
        family_output = output / family
        family_output.mkdir(parents=True)
        (family_output / "index.html").write_text("ok", encoding="utf-8")
        return report

    monkeypatch.setattr(builder, "build_family", fake_build)
    output = tmp_path / "site"
    manifest, changed = builder.build_site(settings, output, tmp_path / "work")

    written_report = json.loads((output / "link-report.json").read_text(encoding="utf-8"))
    assert changed is True
    assert manifest["families"]["australia"]["link_counts"] == counts
    assert written_report["families"]["australia"] == report


def test_incremental_build_reuses_previous_report(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    discovery = Discovery(["australia"], "australia", [], {"australia": "abc"})
    counts = {"exact": 4, "repaired": 1, "placeholder": 0, "ambiguous": 0}
    report = {"family": "australia", "counts": counts, "repairs": [], "placeholders": []}
    previous = tmp_path / "previous"
    (previous / "australia").mkdir(parents=True)
    (previous / "australia" / "index.html").write_text("ok", encoding="utf-8")
    previous_manifest = {
        "pipeline_fingerprint": builder.pipeline_fingerprint(tmp_path),
        "latest": "australia",
        "families": {"australia": {"source_sha": "abc", "archived": False}},
    }
    (previous / "build-manifest.json").write_text(json.dumps(previous_manifest), encoding="utf-8")
    (previous / "link-report.json").write_text(
        json.dumps({"schema_version": 1, "families": {"australia": report}}), encoding="utf-8"
    )

    monkeypatch.setattr(builder, "discover", lambda _settings: discovery)
    monkeypatch.setattr(
        builder,
        "build_family",
        lambda *_args: (_ for _ in ()).throw(AssertionError("family should have been reused")),
    )
    output = tmp_path / "site"
    manifest, changed = builder.build_site(settings, output, tmp_path / "work", previous)

    assert changed is False
    assert manifest["families"]["australia"]["link_counts"] == counts
    assert json.loads((output / "link-report.json").read_text())["families"]["australia"] == report


def test_pipeline_fingerprint_ignores_python_bytecode(tmp_path):
    package = tmp_path / "src" / "sndocs"
    cache = package / "__pycache__"
    cache.mkdir(parents=True)
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("project = {}\n", encoding="utf-8")
    (tmp_path / "pipeline.toml").write_text("site = {}\n", encoding="utf-8")
    (cache / "module.pyc").write_bytes(b"first")
    before = builder.pipeline_fingerprint(tmp_path)
    (cache / "module.pyc").write_bytes(b"different")
    assert builder.pipeline_fingerprint(tmp_path) == before
