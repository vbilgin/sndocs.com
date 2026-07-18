import json
import errno

from sndocs import builder
from sndocs.artifacts import validate_site
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
    counts = builder.empty_link_counts()
    counts["document_links"].update({"exact": 8, "repaired": 2, "missing": 1})
    counts["placeholders"] = 1
    report = {
        "family": "australia",
        "counts": counts,
        "repairs": [],
        "placeholders": [],
        "omitted_images": [],
    }

    monkeypatch.setattr(builder, "discover", lambda _settings, _source: discovery)

    def fake_build(_settings, _discovery, family, _work, output, _source, **_kwargs):
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

    monkeypatch.setattr(builder, "discover", lambda _settings, _source: discovery)
    monkeypatch.setattr(
        builder,
        "build_family",
        lambda *_args: (_ for _ in ()).throw(AssertionError("family should have been reused")),
    )
    output = tmp_path / "site"
    manifest, changed = builder.build_site(settings, output, tmp_path / "work", previous)

    assert changed is False
    upgraded = json.loads((output / "link-report.json").read_text())["families"]["australia"]
    assert manifest["families"]["australia"]["link_counts"] == upgraded["counts"]
    assert upgraded["counts"]["document_links"]["exact"] == 4
    assert upgraded["repairs"] == []
    assert upgraded["legacy_schema"] == 1


def test_archived_family_schema_one_report_is_upgraded(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    discovery = Discovery(["australia"], "australia", [], {"australia": "new"})
    previous = tmp_path / "previous"
    (previous / "xanadu").mkdir(parents=True)
    (previous / "xanadu" / "index.html").write_text("archived", encoding="utf-8")
    (previous / "build-manifest.json").write_text(
        json.dumps(
            {
                "pipeline_fingerprint": "old",
                "latest": "xanadu",
                "families": {"xanadu": {"source_sha": "old", "archived": False}},
            }
        ),
        encoding="utf-8",
    )
    legacy = {
        "family": "xanadu",
        "counts": {"exact": 3, "repaired": 1, "placeholder": 1, "ambiguous": 0},
        "repairs": [],
        "placeholders": [
            {"target": "pub/missing.md", "referring_pages": ["pub/source.md"]}
        ],
    }
    (previous / "link-report.json").write_text(
        json.dumps({"schema_version": 1, "families": {"xanadu": legacy}}),
        encoding="utf-8",
    )

    def fake_build(_settings, _discovery, family, _work, output, _source, **_kwargs):
        family_output = output / family
        family_output.mkdir(parents=True)
        (family_output / "index.html").write_text("current", encoding="utf-8")
        return builder.empty_link_report(family)

    monkeypatch.setattr(builder, "build_family", fake_build)
    output = tmp_path / "site"
    manifest, _ = builder.build_site(
        settings,
        output,
        tmp_path / "work",
        previous,
        discovery_result=discovery,
    )

    report = json.loads((output / "link-report.json").read_text())
    archived = report["families"]["xanadu"]
    assert report["schema_version"] == 2
    assert archived["legacy_schema"] == 1
    assert archived["counts"]["document_links"]["missing"] == 1
    assert archived["placeholders"][0]["referrers"] == [
        {"kind": "document", "path": "pub/source.md"}
    ]
    assert manifest["families"]["xanadu"]["archived"] is True


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


def test_smoke_build_selects_latest_disables_search_and_cleans_family_work(tmp_path, monkeypatch):
    configured = settings_for(tmp_path)
    discovery = Discovery(
        ["australia", "zurich"],
        "australia",
        [],
        {"australia": "new", "zurich": "old"},
    )
    calls = []

    def fake_build(_settings, selected, family, work, output, _source, *, search):
        calls.append((selected.families, family, search))
        (work / family).mkdir(parents=True)
        family_output = output / family
        family_output.mkdir(parents=True)
        (family_output / "index.html").write_text("ok", encoding="utf-8")
        return builder.empty_link_report(family)

    monkeypatch.setattr(builder, "build_family", fake_build)
    output = tmp_path / "site"
    work = tmp_path / "work"
    manifest, _ = builder.build_site(
        configured,
        output,
        work,
        discovery_result=discovery,
        build_profile="smoke",
        cleanup_work=True,
    )

    assert calls == [(["australia"], "australia", False)]
    assert manifest["build_profile"] == "smoke"
    assert list(manifest["families"]) == ["australia"]
    assert not (work / "australia").exists()
    validate_site(output)


def test_reused_family_prefers_hard_links(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    original = source / "index.html"
    original.write_text("ok", encoding="utf-8")
    destination = tmp_path / "destination"

    method = builder.copy_reused_family(source, destination)

    assert method == "hard-linked"
    assert (destination / "index.html").stat().st_ino == original.stat().st_ino


def test_reused_family_falls_back_to_copy(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.html").write_text("ok", encoding="utf-8")
    destination = tmp_path / "destination"

    def cross_device_link(_source, _destination):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(builder.os, "link", cross_device_link)
    method = builder.copy_reused_family(source, destination)

    assert method == "copied"
    assert (destination / "index.html").read_text(encoding="utf-8") == "ok"
