from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

import pytest

from sndocs import builder, cli
from sndocs.artifacts import package_site, validate_site
from sndocs.links import FamilyLinkResolver
from sndocs.models import Discovery, Publication, Settings
from sndocs.transform import rewrite_links, transform_tree


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _index(family: str, area: str, topics: list[str]) -> str:
    links = "\n".join(
        f"- [{topic}](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/"
        f"{family}/markdown/{area}/{topic}.md)"
        for topic in topics
    )
    return f"---\ntitle: {area.title()}\n---\n# {area.title()}\n\n{links}\n"


def test_preview_sample_covers_every_area_deterministically(tmp_path):
    markdown = tmp_path / "markdown"
    _write(markdown / "alpha/index.md", _index("australia", "alpha", ["declared", "other"]))
    for name in ("declared", "other", "third"):
        _write(markdown / f"alpha/{name}.md", f"# {name}\n")
    for name in ("one", "two", "three"):
        _write(markdown / f"beta/{name}.md", f"# {name}\n")
    _write(markdown / "gamma/index.md", _index("australia", "gamma", ["only"]))
    _write(markdown / "gamma/only.md", "# only\n")

    first = builder.select_preview_sample(markdown)
    reordered = tmp_path / "reordered"
    files = sorted(path for path in markdown.rglob("*.md"))
    for path in reversed(files):
        _write(
            reordered / path.relative_to(markdown),
            path.read_text(encoding="utf-8"),
        )
    second = builder.select_preview_sample(reordered)

    assert first == second
    assert first.total_markdown_files == 9
    assert first.source_areas == 3
    assert first.selected_markdown_files == 7
    assert first.selected_topic_files == 5
    assert first.topics_by_area["alpha"][0] == PurePosixPath("alpha/declared.md")
    assert len(first.topics_by_area["alpha"]) == 2
    assert len(first.topics_by_area["beta"]) == 2
    assert first.topics_by_area["gamma"] == (PurePosixPath("gamma/only.md"),)
    assert PurePosixPath("alpha/index.md") in first.paths
    assert PurePosixPath("gamma/index.md") in first.paths


def test_preview_links_externalize_only_existing_omitted_documents(tmp_path):
    markdown = tmp_path / "markdown"
    for name in ("selected", "omitted"):
        _write(markdown / f"area/{name}.md", f"# {name}\n")
    resolver = FamilyLinkResolver(markdown, "australia")
    stats = {"externalized_links": 0}
    body = (
        "[Selected](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/"
        "australia/markdown/area/selected.md)\n"
        "[Omitted](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/"
        "australia/markdown/area/omitted.md)\n"
        "[Missing](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/"
        "australia/markdown/area/missing.md)\n"
        "[Other family](https://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/"
        "zurich/markdown/area/selected.md)\n"
    )

    rewritten = rewrite_links(
        body,
        "australia",
        PurePosixPath("area/selected.md"),
        {"australia", "zurich"},
        "ServiceNow/ServiceNowDocs",
        resolver,
        {PurePosixPath("area/selected.md")},
        stats,
    )

    assert "[Selected](selected.md)" in rewritten
    assert (
        "https://github.com/ServiceNow/ServiceNowDocs/blob/australia/"
        "markdown/area/omitted.md"
    ) in rewritten
    assert "[Missing](missing.md)" in rewritten
    assert (
        "https://github.com/ServiceNow/ServiceNowDocs/blob/zurich/"
        "markdown/area/selected.md"
    ) in rewritten
    assert stats == {"externalized_links": 2}
    assert PurePosixPath("area/missing.md") in resolver.missing


def test_filtered_transform_keeps_assets_and_adds_preview_banner(tmp_path):
    markdown = tmp_path / "markdown"
    _write(markdown / "area/selected.md", "# Selected\n")
    _write(markdown / "area/omitted.md", "# Omitted\n")
    _write(markdown / "area/image.png", "image")
    docs = tmp_path / "docs"

    transform_tree(
        markdown,
        docs,
        "australia",
        {"australia"},
        "ServiceNow/ServiceNowDocs",
        include_paths={PurePosixPath("area/selected.md")},
    )

    assert (docs / "area/selected.md").is_file()
    assert "Incomplete preview" in (docs / "area/selected.md").read_text(encoding="utf-8")
    assert not (docs / "area/omitted.md").exists()
    assert (docs / "area/image.png").read_text(encoding="utf-8") == "image"


class _FixtureSource:
    def __init__(self, template: Path):
        self.template = template

    def materialize(
        self,
        _settings: Settings,
        _family: str,
        _sha: str,
        destination: Path,
    ) -> None:
        shutil.copytree(self.template, destination)


def test_preview_profile_builds_strict_searchable_sample(tmp_path):
    template = tmp_path / "template"
    markdown = template / "markdown"
    topics = ["first", "second", "third"]
    _write(markdown / "area/index.md", _index("australia", "area", topics))
    for topic in topics:
        _write(
            markdown / f"area/{topic}.md",
            "---\ntitle: " + topic.title() + "\n---\n# " + topic.title() + "\n",
        )
    settings = Settings(
        tmp_path / "pipeline.toml",
        "sndocs",
        "https://sndocs.com",
        "Mirror",
        "ServiceNow/ServiceNowDocs",
        "llms.txt",
        (),
        "sndocs-site",
    )
    discovery = Discovery(
        ["australia"],
        "australia",
        [Publication("Area", "area", "url")],
        {"australia": "sha"},
    )
    selected = builder.select_preview_sample(markdown)
    omitted = ({PurePosixPath(f"area/{topic}.md") for topic in topics} - set(selected.paths)).pop()
    output = tmp_path / "site"

    manifest, changed = builder.build_site(
        settings,
        output,
        tmp_path / "work",
        source_repository=_FixtureSource(template),
        discovery_result=discovery,
        build_profile="preview",
    )

    assert changed is True
    assert manifest["build_profile"] == "preview"
    assert manifest["families"]["australia"]["sample"] == {
        "strategy": builder.PREVIEW_STRATEGY,
        "source_markdown_files": 4,
        "source_areas": 1,
        "selected_markdown_files": 3,
        "selected_topic_files": 2,
        "externalized_links": 1,
    }
    assert (output / "australia/preview-sample/index.html").is_file()
    assert not (
        output / "australia" / omitted.with_suffix("").as_posix() / "index.html"
    ).exists()
    rendered_index = (output / "australia/area/index.html").read_text(encoding="utf-8")
    assert f"github.com/ServiceNow/ServiceNowDocs/blob/australia/markdown/{omitted}" in rendered_index
    validate_site(output)
    with pytest.raises(ValueError, match="preview builds cannot be packaged"):
        package_site(output, tmp_path / "artifacts", "site")


def test_preview_cli_builds_validates_and_serves_all_selected_families(
    tmp_path, monkeypatch
):
    config = tmp_path / "pipeline.toml"
    config.write_text(
        '[site]\nname = "test"\n[upstream]\nrepository = "owner/repo"\n',
        encoding="utf-8",
    )
    discovery = Discovery(
        ["australia", "zurich"],
        "australia",
        [],
        {"australia": "one", "zurich": "two"},
    )
    monkeypatch.setattr(cli, "discover", lambda *_args, **_kwargs: discovery)
    observed: dict = {}

    def fake_build(_settings, output, _work, *_args, **kwargs):
        observed["profile"] = kwargs["build_profile"]
        observed["families"] = list(_args[-1].families)
        output.mkdir(parents=True)
        return {
            "latest": "australia",
            "families": {"australia": {}, "zurich": {}},
            "build_profile": "preview",
        }, True

    monkeypatch.setattr(cli, "build_site", fake_build)
    monkeypatch.setattr(cli, "validate_site", lambda output: observed.setdefault("validated", output))
    monkeypatch.setattr(
        cli,
        "_serve_site",
        lambda output, bind, port: observed.update(
            {"served": output, "bind": bind, "port": port}
        ),
    )
    output = tmp_path / "site"

    assert cli.main([
        "--config",
        str(config),
        "preview",
        "--output",
        str(output),
    ]) == 0

    assert observed == {
        "profile": "preview",
        "families": ["australia", "zurich"],
        "validated": output.resolve(),
        "served": output.resolve(),
        "bind": "127.0.0.1",
        "port": 0,
    }


def test_preview_clean_waits_for_successful_discovery(tmp_path, monkeypatch):
    config = tmp_path / "pipeline.toml"
    config.write_text(
        '[site]\nname = "test"\n[upstream]\nrepository = "owner/repo"\n',
        encoding="utf-8",
    )
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "discover",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad source")),
    )

    with pytest.raises(SystemExit):
        cli.main([
            "--config",
            str(config),
            "preview",
            "--output",
            str(output),
            "--clean",
        ])

    assert marker.read_text(encoding="utf-8") == "keep"


def test_preview_rejects_json_and_build_only_options(tmp_path):
    config = tmp_path / "pipeline.toml"
    config.write_text(
        '[site]\nname = "test"\n[upstream]\nrepository = "owner/repo"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        cli.main([
            "--config",
            str(config),
            "--json",
            "preview",
            "--output",
            str(tmp_path / "site"),
        ])
    with pytest.raises(SystemExit):
        cli.parser().parse_args([
            "preview",
            "--output",
            str(tmp_path / "site"),
            "--dry-run",
        ])


def test_preview_profile_is_not_reused_as_production(tmp_path, monkeypatch):
    previous = tmp_path / "previous"
    (previous / "australia").mkdir(parents=True)
    (previous / "build-manifest.json").write_text(
        '{"pipeline_fingerprint":"same","build_profile":"preview","latest":"australia",'
        '"families":{"australia":{"source_sha":"sha"}}}',
        encoding="utf-8",
    )
    settings = Settings(
        tmp_path / "pipeline.toml",
        "sndocs",
        "",
        "",
        "owner/repo",
        "llms.txt",
        (),
        "site",
    )
    discovery = Discovery(["australia"], "australia", [], {"australia": "sha"})
    monkeypatch.setattr(builder, "pipeline_fingerprint", lambda _settings: "same")

    plan = builder.plan_build(
        settings,
        previous,
        discovery,
        build_profile="production",
    )

    assert plan["actions"][0] == {
        "family": "australia",
        "action": "rebuild",
        "reason": "build profile changed",
    }
