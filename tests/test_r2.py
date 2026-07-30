from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sndocs.r2 import TRANSFER_ENV, R2Client, R2Config, R2Error

CONFIG = R2Config(
    bucket="sndocs-production",
    endpoint="https://account.r2.cloudflarestorage.com",
    profile="sndocs-r2",
)


class FakeRunner:
    """Records invocations and replays queued results."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[list[str]] = []
        self.envs: list[dict] = []

    def __call__(self, argv, env=None, capture_output=False):
        self.calls.append(list(argv))
        self.envs.append(env or {})
        result = self.results.pop(0) if self.results else _ok()
        if callable(result):
            result = result(argv)
        return result


def _ok(stdout: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b"")


def _fail(stderr: bytes, code: int = 1) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=b"", stderr=stderr)


def test_configuration_from_environment_fails_closed():
    with pytest.raises(R2Error, match="SNDOCS_R2_BUCKET"):
        R2Config.from_env({"CLOUDFLARE_ACCOUNT_ID": "account"})
    with pytest.raises(R2Error, match="CLOUDFLARE_ACCOUNT_ID"):
        R2Config.from_env({"SNDOCS_R2_BUCKET": "bucket"})

    config = R2Config.from_env(
        {
            "SNDOCS_R2_BUCKET": "bucket",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "AWS_PROFILE": "sndocs-r2",
        }
    )

    assert config.endpoint == "https://account.r2.cloudflarestorage.com"
    assert config.profile == "sndocs-r2"


def test_every_invocation_carries_the_r2_checksum_environment():
    runner = FakeRunner(_ok(b"null"))
    client = R2Client(CONFIG, runner)

    client.list_objects()

    env = runner.envs[0]
    for key, value in TRANSFER_ENV.items():
        assert env[key] == value
    assert "PATH" in env, "the real environment must be inherited"


def test_listing_projects_keys_sizes_and_timestamps_without_truncation():
    payload = json.dumps(
        [{"Key": "releases/a.json", "Size": 12, "LastModified": "2026-07-01T00:00:00Z"}]
    ).encode()
    runner = FakeRunner(_ok(payload))
    client = R2Client(CONFIG, runner)

    objects = client.list_objects("releases/")

    assert objects == [
        {"Key": "releases/a.json", "Size": 12, "LastModified": "2026-07-01T00:00:00Z"}
    ]
    argv = runner.calls[0]
    assert argv[:3] == ["aws", "s3api", "list-objects-v2"]
    assert "--endpoint-url" in argv and CONFIG.endpoint in argv
    assert "--profile" in argv and "sndocs-r2" in argv
    assert argv[argv.index("--prefix") + 1] == "releases/"
    assert "LastModified:LastModified" in argv[argv.index("--query") + 1]
    assert "--max-items" not in argv, "--max-items would truncate the listing"


def test_empty_listing_is_an_empty_list_not_none():
    client = R2Client(CONFIG, FakeRunner(_ok(b"null")))

    assert client.list_objects("content/absent/") == []


def test_missing_object_reads_as_none_but_other_failures_raise():
    client = R2Client(CONFIG, FakeRunner(_fail(b"An error occurred (NoSuchKey) ...")))
    assert client.get_bytes("pointers/production.json") is None

    client = R2Client(CONFIG, FakeRunner(_fail(b"Access Denied")))
    with pytest.raises(R2Error, match="Access Denied"):
        client.get_bytes("pointers/production.json")


def test_reading_an_object_returns_its_body():
    def write_object(argv):
        Path(argv[-1]).write_bytes(b'{"release_id": "abc"}')
        return _ok()

    client = R2Client(CONFIG, FakeRunner(write_object))

    assert client.get_bytes("pointers/production.json") == b'{"release_id": "abc"}'


def test_put_bytes_sends_content_type_and_cache_control():
    runner = FakeRunner()
    client = R2Client(CONFIG, runner)

    client.put_bytes(
        "pointers/preview.json",
        b"{}",
        content_type="application/json",
        cache_control="no-store",
    )

    argv = runner.calls[0]
    assert argv[:3] == ["aws", "s3api", "put-object"]
    assert argv[argv.index("--key") + 1] == "pointers/preview.json"
    assert argv[argv.index("--content-type") + 1] == "application/json"
    assert argv[argv.index("--cache-control") + 1] == "no-store"
    assert Path(argv[argv.index("--body") + 1]).name == "body"


def test_tree_transfers_are_recursive_and_slash_terminated(tmp_path):
    runner = FakeRunner(_ok(), _ok())
    client = R2Client(CONFIG, runner)
    local = tmp_path / "tree"
    local.mkdir()

    client.put_tree(local, "content/zurich/abc")
    client.get_tree("releases/def/root", tmp_path / "root")

    upload, download = runner.calls
    assert upload[:3] == ["aws", "s3", "cp"]
    assert upload[-3:] == [
        str(local),
        "s3://sndocs-production/content/zurich/abc/",
        "--recursive",
    ]
    assert download[-3:] == [
        "s3://sndocs-production/releases/def/root/",
        str(tmp_path / "root"),
        "--recursive",
    ]


def test_delete_batch_passes_the_payload_as_a_file_uri(tmp_path):
    payload = tmp_path / "batch-0001.json"
    payload.write_text("{}", encoding="utf-8")
    runner = FakeRunner(_ok(b'{"Deleted": []}'))
    client = R2Client(CONFIG, runner)

    result = client.delete_batch(payload)

    argv = runner.calls[0]
    assert argv[:3] == ["aws", "s3api", "delete-objects"]
    assert argv[argv.index("--delete") + 1] == f"file://{payload}"
    assert result == {"Deleted": []}
