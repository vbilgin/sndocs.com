from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import sndocs.source as source_module
from sndocs import builder
from sndocs.cli import main, parser
from sndocs.discovery import discover
from sndocs.models import Settings
from sndocs.source import LocalSource, clone_local_source


LLMS = '''
- "australia" : "australia" -- latest
- "zurich" : "zurich" -- previous
## Documents
- [Test](https://raw.githubusercontent.com/owner/repo/australia/markdown/test/index.md)
'''


def run(*arguments: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def settings(root: Path) -> Settings:
    return Settings(root, "site", "", "", "owner/repo", "llms.txt", (), "site")


@pytest.fixture
def local_clone(tmp_path: Path) -> tuple[Path, Settings, dict[str, str]]:
    repository = tmp_path / "source"
    repository.mkdir()
    run("init", "-b", "main", cwd=repository)
    run("config", "user.name", "Test", cwd=repository)
    run("config", "user.email", "test@example.com", cwd=repository)
    (repository / "llms.txt").write_text(LLMS, encoding="utf-8")
    run("add", "llms.txt", cwd=repository)
    run("commit", "-m", "metadata", cwd=repository)
    main_sha = run("rev-parse", "HEAD", cwd=repository)
    shas: dict[str, str] = {}
    for family in ("australia", "zurich"):
        run("switch", "--orphan", family, cwd=repository)
        page = repository / "markdown" / "test" / "index.md"
        page.parent.mkdir(parents=True)
        page.write_text(f"# {family}\n", encoding="utf-8")
        run("add", ".", cwd=repository)
        run("commit", "-m", family, cwd=repository)
        shas[family] = run("rev-parse", "HEAD", cwd=repository)
    run("switch", "main", cwd=repository)
    run("remote", "add", "origin", "git@github.com:owner/repo.git", cwd=repository)
    run("update-ref", "refs/remotes/origin/main", main_sha, cwd=repository)
    for family, sha in shas.items():
        run("update-ref", f"refs/remotes/origin/{family}", sha, cwd=repository)
    run("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main", cwd=repository)
    return repository, settings(tmp_path), shas


def test_local_discovery_and_materialization_are_offline(local_clone, tmp_path):
    repository, configured, shas = local_clone
    source = LocalSource(repository, configured)

    result = discover(configured, source)
    assert result.families == ["australia", "zurich"]
    assert result.shas == shas

    before = run("status", "--porcelain=v2", "--branch", cwd=repository)
    for family in result.families:
        destination = tmp_path / f"export-{family}"
        source.materialize(configured, family, result.shas[family], destination)
        assert (destination / "markdown" / "test" / "index.md").read_text() == f"# {family}\n"
    assert run("status", "--porcelain=v2", "--branch", cwd=repository) == before


def test_local_materialization_streams_git_archive(local_clone, tmp_path, monkeypatch):
    repository, configured, shas = local_clone
    source = LocalSource(repository, configured)
    original_popen = source_module.subprocess.Popen
    calls = []

    def recording_popen(arguments, *args, **kwargs):
        calls.append(arguments)
        return original_popen(arguments, *args, **kwargs)

    monkeypatch.setattr(source_module.subprocess, "Popen", recording_popen)
    destination = tmp_path / "export"
    source.materialize(configured, "australia", shas["australia"], destination)

    assert calls == [[
        "git", "-C", str(repository.resolve()), "archive", "--format=tar", shas["australia"]
    ]]
    assert (destination / "markdown" / "test" / "index.md").exists()


def test_local_build_manifest_and_incremental_reuse_use_commit_shas(local_clone, tmp_path, monkeypatch):
    repository, configured, shas = local_clone
    source = LocalSource(repository, configured)
    result = discover(configured, source)

    def fake_build(_settings, _discovery, family, _work, output, _source, **_kwargs):
        family_output = output / family
        family_output.mkdir(parents=True)
        (family_output / "index.html").write_text("ok")
        return builder.empty_link_report(family)

    monkeypatch.setattr(builder, "build_family", fake_build)
    first = tmp_path / "first"
    manifest, changed = builder.build_site(
        configured, first, tmp_path / "work-1", source_repository=source, discovery_result=result
    )
    assert changed is True
    assert {family: record["source_sha"] for family, record in manifest["families"].items()} == shas

    monkeypatch.setattr(
        builder, "build_family",
        lambda *_args: (_ for _ in ()).throw(AssertionError("families should be reused")),
    )
    second = tmp_path / "second"
    _, changed = builder.build_site(
        configured, second, tmp_path / "work-2", first, source, result
    )
    assert changed is False


@pytest.mark.parametrize("untracked", [False, True])
def test_local_source_rejects_dirty_repository(local_clone, untracked):
    repository, configured, _ = local_clone
    if untracked:
        (repository / "untracked").write_text("dirty")
    else:
        (repository / "llms.txt").write_text("dirty")
    with pytest.raises(ValueError, match="must be clean"):
        LocalSource(repository, configured)


def test_local_source_rejects_mismatched_and_ambiguous_remotes(local_clone):
    repository, configured, _ = local_clone
    run("remote", "set-url", "origin", "https://github.com/other/repo.git", cwd=repository)
    with pytest.raises(ValueError, match="no matching remote"):
        LocalSource(repository, configured)
    run("remote", "set-url", "origin", "https://github.com/owner/repo.git", cwd=repository)
    run("remote", "add", "duplicate", "git@github.com:owner/repo.git", cwd=repository)
    with pytest.raises(ValueError, match="ambiguous matching remotes"):
        LocalSource(repository, configured)


def test_local_source_requires_default_and_family_refs(local_clone):
    repository, configured, _ = local_clone
    run("symbolic-ref", "--delete", "refs/remotes/origin/HEAD", cwd=repository)
    with pytest.raises(ValueError, match="default-branch metadata"):
        LocalSource(repository, configured)
    run("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main", cwd=repository)
    run("update-ref", "-d", "refs/remotes/origin/zurich", cwd=repository)
    source = LocalSource(repository, configured)
    with pytest.raises(ValueError, match="missing family refs: zurich"):
        discover(configured, source)


def test_refresh_fetches_only_when_requested(local_clone, monkeypatch):
    repository, configured, _ = local_clone
    original_run = source_module.subprocess.run
    fetches: list[list[str]] = []

    def recording_run(arguments, *args, **kwargs):
        if "fetch" in arguments:
            fetches.append(arguments)
            return subprocess.CompletedProcess(arguments, 0, "", "")
        return original_run(arguments, *args, **kwargs)

    monkeypatch.setattr(source_module.subprocess, "run", recording_run)
    LocalSource(repository, configured)
    assert fetches == []
    LocalSource(repository, configured, refresh=True)
    assert fetches == [["git", "-C", str(repository.resolve()), "fetch", "--prune", "origin"]]


def test_source_check_cli_is_offline_and_returns_json(local_clone, tmp_path, monkeypatch, capsys):
    repository, _, _ = local_clone
    config = tmp_path / "pipeline.toml"
    config.write_text('[site]\n[upstream]\nrepository = "owner/repo"\n', encoding="utf-8")
    original_run = source_module.subprocess.run

    def no_fetch(arguments, *args, **kwargs):
        assert "fetch" not in arguments
        return original_run(arguments, *args, **kwargs)

    monkeypatch.setattr(source_module.subprocess, "run", no_fetch)
    assert main(["source", "check", str(repository), "--config", str(config), "--json"]) == 0
    output = __import__("json").loads(capsys.readouterr().out)
    assert output["status"] == "ok"
    assert output["families"] == ["australia", "zurich"]


def test_clone_destination_must_not_exist(tmp_path):
    destination = tmp_path / "exists"
    destination.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        clone_local_source(destination, settings(tmp_path))


def test_removed_source_cli_options_are_rejected():
    with pytest.raises(SystemExit):
        parser().parse_args(["discover", "--source-repo", "one", "--clone-source", "two"])


def test_source_update_requires_a_path():
    with pytest.raises(SystemExit):
        parser().parse_args(["source", "update"])


def test_invalid_local_source_does_not_remove_build_output(local_clone, tmp_path):
    repository, _, _ = local_clone
    (repository / "dirty").write_text("dirty")
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("preserved")
    config = tmp_path / "pipeline.toml"
    config.write_text('[site]\n[upstream]\nrepository = "owner/repo"\n', encoding="utf-8")

    with pytest.raises(SystemExit):
        main([
            "--config", str(config), "build", "--output", str(output),
            "--source", str(repository), "--clean",
        ])
    assert marker.read_text() == "preserved"
