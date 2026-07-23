from pathlib import Path

import pytest

from sndocs import cli
from sndocs.models import Discovery


def write_config(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
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
    repository = tmp_path / "repository"
    repository.mkdir()
    config = write_config(repository / "local" / "test")
    monkeypatch.chdir(repository)
    monkeypatch.setattr(cli, "discover", lambda *_args: discovery())
    observed = []

    def fake_build(_settings, _output, work, *_args, **kwargs):
        observed.append((work, kwargs))
        (work / "marker").write_text("temporary", encoding="utf-8")
        return manifest(), True

    monkeypatch.setattr(cli, "build_site", fake_build)
    cli.main(["--config", str(config), "build", "--output", str(tmp_path / "site")])

    work, kwargs = observed[0]
    assert work.parent == repository / ".temp"
    assert work.name.startswith("sndocs-")
    assert kwargs["cleanup_work"] is True
    assert not work.exists()


def test_automatic_workspace_is_removed_after_failure(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    config = write_config(repository / "local" / "test")
    monkeypatch.chdir(repository)
    monkeypatch.setattr(cli, "discover", lambda *_args: discovery())
    observed = []

    def failing_build(_settings, _output, work, *_args, **_kwargs):
        observed.append(work)
        (work / "marker").write_text("temporary", encoding="utf-8")
        raise RuntimeError("failed")

    monkeypatch.setattr(cli, "build_site", failing_build)
    with pytest.raises(SystemExit, match="2"):
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


def test_serve_defaults_and_graceful_shutdown(tmp_path, monkeypatch, capsys):
    config = write_config(tmp_path)
    site = tmp_path / "site"
    site.mkdir()
    observed = {}

    class FakeServer:
        server_address = ("127.0.0.1", 8000)

        def __init__(self, address, handler):
            observed["address"] = address
            observed["handler"] = handler

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            observed["closed"] = True

    monkeypatch.setattr(cli.http.server, "ThreadingHTTPServer", FakeServer)

    assert cli.main(["--config", str(config), "serve", "--site", str(site)]) == 0

    assert observed["address"] == ("127.0.0.1", 8000)
    assert observed["handler"].keywords["directory"] == str(site.resolve())
    assert observed["closed"] is True
    output = capsys.readouterr().out
    assert "http://127.0.0.1:8000/" in output
    assert "Preview stopped." in output


def test_serve_accepts_bind_and_port_overrides(tmp_path, monkeypatch):
    config = write_config(tmp_path)
    site = tmp_path / "built-site"
    site.mkdir()
    observed = {}

    class FakeServer:
        server_address = ("localhost", 4321)

        def __init__(self, address, _handler):
            observed["address"] = address

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(cli.http.server, "ThreadingHTTPServer", FakeServer)

    cli.main([
        "--config", str(config), "serve", "--site", str(site),
        "--bind", "localhost", "--port", "4321",
    ])

    assert observed["address"] == ("localhost", 4321)


def test_serve_port_zero_reports_allocated_port(tmp_path, monkeypatch, capsys):
    config = write_config(tmp_path)
    site = tmp_path / "built-site"
    site.mkdir()
    observed = {}

    class FakeServer:
        server_address = ("127.0.0.1", 54321)

        def __init__(self, address, _handler):
            observed["address"] = address

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(cli.http.server, "ThreadingHTTPServer", FakeServer)
    cli.main(["--config", str(config), "serve", "--site", str(site), "--port", "0"])
    assert observed["address"] == ("127.0.0.1", 0)
    assert "http://127.0.0.1:54321/" in capsys.readouterr().out


def test_serve_rejects_missing_site(tmp_path, capsys):
    config = write_config(tmp_path)

    with pytest.raises(SystemExit, match="2"):
        cli.main([
            "--config", str(config), "serve", "--site", str(tmp_path / "missing")
        ])

    error = capsys.readouterr().err
    assert "site directory does not exist" in error
    assert "build it first or pass --site PATH" in error
