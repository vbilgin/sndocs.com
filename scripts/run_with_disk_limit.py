from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--limit-gib", type=float, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("command", nargs=argparse.REMAINDER)
    return result


def main() -> int:
    args = parser().parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("a command is required after --")
    baseline_free = shutil.disk_usage(Path.cwd()).free
    requested_limit = int(args.limit_gib * 1024**3)
    reserve = 2 * 1024**3
    limit = min(requested_limit, max(0, baseline_free - reserve))
    peak = 0
    process = subprocess.Popen(command, start_new_session=True)
    exceeded = False
    while process.poll() is None:
        consumed = max(0, baseline_free - shutil.disk_usage(Path.cwd()).free)
        peak = max(peak, consumed)
        if consumed >= limit:
            exceeded = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            break
        time.sleep(2)
    consumed = max(0, baseline_free - shutil.disk_usage(Path.cwd()).free)
    peak = max(peak, consumed)
    result = {
        "command": command,
        "baseline_free_bytes": baseline_free,
        "requested_limit_bytes": requested_limit,
        "limit_bytes": limit,
        "reserved_free_bytes": reserve,
        "peak_consumed_bytes": peak,
        "peak_consumed_gib": round(peak / 1024**3, 3),
        "limit_exceeded": exceeded,
        "exit_code": process.returncode,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if exceeded:
        print(
            f"build stopped after consuming {result['peak_consumed_gib']} GiB "
            f"(effective limit {round(limit / 1024**3, 3)} GiB)",
            file=sys.stderr,
        )
        return 75
    return process.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
