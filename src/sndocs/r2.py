"""Thin, injectable wrapper around the ``aws`` CLI for the private R2 origin.

This module owns every byte that leaves or enters the bucket. It deliberately
contains no release logic: callers in ``publish_cli`` decide what to transfer,
and ``deployment`` decides whether a transfer was correct.

The ``aws`` CLI is used instead of an SDK because the verification contract in
``deployment`` is already shaped around ``list-objects-v2`` output, and because
``aws s3 cp --recursive`` already performs the concurrent multipart upload of a
large family tree that this project would otherwise have to reimplement.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ENDPOINT_TEMPLATE = "https://{account_id}.r2.cloudflarestorage.com"

# R2 rejects the default AWS CLI v2 checksum behaviour; these mirror the values
# the retired GitHub Actions workflow set for every step that touched S3.
TRANSFER_ENV = {
    "AWS_DEFAULT_REGION": "auto",
    "AWS_REQUEST_CHECKSUM_CALCULATION": "when_supported",
    "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_supported",
}

MISSING_KEY_MARKERS = ("NoSuchKey", "Not Found", "404")

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


class R2Error(RuntimeError):
    """An ``aws`` invocation failed."""


@dataclass(frozen=True)
class R2Config:
    bucket: str
    endpoint: str
    profile: str | None = None

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> R2Config:
        source = os.environ if environ is None else environ
        bucket = source.get("SNDOCS_R2_BUCKET", "").strip()
        account_id = source.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        missing = [
            name
            for name, value in (
                ("SNDOCS_R2_BUCKET", bucket),
                ("CLOUDFLARE_ACCOUNT_ID", account_id),
            )
            if not value
        ]
        if missing:
            raise R2Error(
                "R2 configuration is incomplete; set " + ", ".join(missing)
            )
        profile = source.get("AWS_PROFILE", "").strip() or None
        return cls(
            bucket=bucket,
            endpoint=ENDPOINT_TEMPLATE.format(account_id=account_id),
            profile=profile,
        )


class R2Client:
    def __init__(self, config: R2Config, runner: Runner = subprocess.run) -> None:
        self.config = config
        self._runner = runner

    # -- invocation ---------------------------------------------------------

    def _base(self, service: str, operation: str) -> list[str]:
        argv = ["aws", service, operation, "--endpoint-url", self.config.endpoint]
        if self.config.profile:
            argv += ["--profile", self.config.profile]
        return argv

    def _env(self) -> dict[str, str]:
        return {**os.environ, **TRANSFER_ENV}

    def _run(self, argv: list[str], *, allow_missing: bool = False):
        completed = self._runner(argv, env=self._env(), capture_output=True)
        if completed.returncode == 0:
            return completed
        stderr = (completed.stderr or b"").decode("utf-8", "replace").strip()
        if allow_missing and any(marker in stderr for marker in MISSING_KEY_MARKERS):
            return None
        raise R2Error(f"{' '.join(argv[:3])} failed: {stderr or completed.returncode}")

    def _json(self, argv: list[str]):
        completed = self._run(argv)
        assert completed is not None
        payload = (completed.stdout or b"").decode("utf-8").strip()
        return json.loads(payload) if payload else None

    def _uri(self, key: str) -> str:
        return f"s3://{self.config.bucket}/{key}"

    # -- reads --------------------------------------------------------------

    def list_objects(self, prefix: str = "") -> list[dict]:
        """Return every object under ``prefix`` as ``{Key, Size, LastModified}``.

        ``LastModified`` is retained because cleanup planning uses it for the
        grace window. The AWS CLI paginates ``list-objects-v2`` itself and
        merges the pages before applying ``--query``; do not add ``--max-items``,
        which would truncate the result and silently under-protect a cleanup
        plan. Cross-check large listings with :meth:`count_objects`.
        """
        argv = self._base("s3api", "list-objects-v2") + [
            "--bucket",
            self.config.bucket,
            "--page-size",
            "1000",
            "--query",
            "Contents[].{Key:Key,Size:Size,LastModified:LastModified}",
        ]
        if prefix:
            argv += ["--prefix", prefix]
        return self._json(argv) or []

    def count_objects(self, prefix: str = "") -> int:
        argv = self._base("s3api", "list-objects-v2") + [
            "--bucket",
            self.config.bucket,
            "--page-size",
            "1000",
            "--query",
            "length(Contents)",
        ]
        if prefix:
            argv += ["--prefix", prefix]
        return self._json(argv) or 0

    def get_bytes(self, key: str) -> bytes | None:
        """Return the object body, or ``None`` when the key does not exist."""
        with tempfile.TemporaryDirectory(prefix="sndocs-r2-") as scratch:
            destination = Path(scratch) / "object"
            argv = self._base("s3api", "get-object") + [
                "--bucket",
                self.config.bucket,
                "--key",
                key,
                str(destination),
            ]
            if self._run(argv, allow_missing=True) is None:
                return None
            return destination.read_bytes()

    def get_tree(self, prefix: str, local: Path) -> None:
        local.mkdir(parents=True, exist_ok=True)
        argv = self._base("s3", "cp") + [
            self._uri(prefix.rstrip("/") + "/"),
            str(local),
            "--recursive",
        ]
        self._run(argv)

    # -- writes -------------------------------------------------------------

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        cache_control: str | None = None,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="sndocs-r2-") as scratch:
            body = Path(scratch) / "body"
            body.write_bytes(data)
            argv = self._base("s3api", "put-object") + [
                "--bucket",
                self.config.bucket,
                "--key",
                key,
                "--body",
                str(body),
                "--content-type",
                content_type,
            ]
            if cache_control:
                argv += ["--cache-control", cache_control]
            self._run(argv)

    def put_tree(self, local: Path, prefix: str) -> None:
        argv = self._base("s3", "cp") + [
            str(local),
            self._uri(prefix.rstrip("/") + "/"),
            "--recursive",
        ]
        self._run(argv)

    def delete_batch(self, payload: Path) -> dict:
        argv = self._base("s3api", "delete-objects") + [
            "--bucket",
            self.config.bucket,
            "--delete",
            f"file://{payload}",
        ]
        return self._json(argv) or {}
