from pathlib import Path

import pytest

from sndocs import cli
from sndocs.models import Discovery


def write_config(root: Path) -> Path:
    config = root / "pipeline.toml"
    config.write_text(
        '[site]\nname = "test"\n[upstream]\nrepository = "owner/repo"\n',
        encoding="utf-8",
    )
    return config


def discovery() -> Discovery:
    return Discovery(["australia"], "australia", [], {"australia": "abc"})


def manifest() -> dict:
    return {"latest": "australia", "families": {}, "build_profile": "production"}


def test_automatic_workspace_is_inside_repo_and_removed(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    monkeypatch.setattr(cli, "discover", lambda *_args: discovery())
    observed = []

    def fake_build(_settings, _output, work, *_args, **kwargs):
        observed.append((work, kwargs))
        (work / "marker").write_text("temporary", encoding="utf-8")
        return manifest(), True

    monkeypatch.setattr(cli, "build_site", fake_build)
    cli.main(["--config", str(config), "build", "--output", str(tmp_path / "site")])

    work, kwargs = observed[0]
    assert work.parent == tmp_path / ".temp"
    assert work.name.startswith("sndocs-")
    assert kwargs["cleanup_work"] is True
    assert not work.exists()


def test_automatic_workspace_is_removed_after_failure(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    monkeypatch.setattr(cli, "discover", lambda *_args: discovery())
    observed = []

    def failing_build(_settings, _output, work, *_args, **_kwargs):
        observed.append(work)
        (work / "marker").write_text("temporary", encoding="utf-8")
        raise RuntimeError("failed")

    monkeypatch.setattr(cli, "build_site", failing_build)
    with pytest.raises(RuntimeError, match="failed"):
        cli.main(["--config", str(config), "build", "--output", str(tmp_path / "site")])

    assert not observed[0].exists()


def test_explicit_workspace_is_preserved(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    monkeypatch.setattr(cli, "discover", lambda *_args: discovery())
    work = tmp_path / "diagnostic-work"

    def fake_build(_settings, _output, selected_work, *_args, **kwargs):
        assert kwargs.get("cleanup_work", False) is False
        (selected_work / "marker").write_text("preserved", encoding="utf-8")
        return manifest(), True

    monkeypatch.setattr(cli, "build_site", fake_build)
    cli.main([
        "--config", str(config), "build", "--output", str(tmp_path / "site"),
        "--work-dir", str(work),
    ])

    assert (work / "marker").read_text(encoding="utf-8") == "preserved"
