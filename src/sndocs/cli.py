from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .artifacts import package_site, validate_site
from .builder import MANIFEST_NAME, build_site
from .config import load_settings
from .discovery import discover
from .source import LocalSource, RemoteSource, clone_local_source


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="sndocs", description="Build the sndocs.com static documentation mirror")
    result.add_argument("--config", type=Path, default=Path("pipeline.toml"))
    commands = result.add_subparsers(dest="command", required=True)
    discover_command = commands.add_parser("discover", help="discover upstream families and publication metadata")
    build = commands.add_parser("build", help="build or incrementally assemble the complete site")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--work-dir", type=Path)
    build.add_argument("--previous-site", type=Path)
    build.add_argument("--github-output", type=Path)
    for command in (discover_command, build):
        sources = command.add_mutually_exclusive_group()
        sources.add_argument("--source-repo", type=Path, help="use an existing local upstream clone")
        sources.add_argument("--clone-source", type=Path, help="clone upstream here, then use the clone")
        command.add_argument("--refresh-source", action="store_true", help="fetch the existing local source before use")
    package = commands.add_parser("package", help="validate and package a built site")
    package.add_argument("--site", type=Path, required=True)
    package.add_argument("--destination", type=Path, required=True)
    commands.add_parser("validate", help="validate the default ./site output").add_argument("--site", type=Path, default=Path("site"))
    return result


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    settings = load_settings(args.config.resolve())
    if args.command in {"discover", "build"}:
        if args.refresh_source and not args.source_repo:
            argument_parser.error("--refresh-source requires --source-repo")
        try:
            if args.clone_source:
                source_repository = clone_local_source(args.clone_source, settings)
            elif args.source_repo:
                source_repository = LocalSource(args.source_repo, settings, refresh=args.refresh_source)
            else:
                source_repository = RemoteSource()
            discovery_result = discover(settings, source_repository)
        except (ValueError, subprocess.CalledProcessError) as error:
            argument_parser.error(str(error))
    if args.command == "discover":
        print(json.dumps(discovery_result.to_dict(), indent=2))
        return 0
    if args.command == "build":
        output = args.output.resolve()
        previous_site = args.previous_site.resolve() if args.previous_site else None
        if output.exists():
            shutil.rmtree(output)
        if args.work_dir:
            args.work_dir.mkdir(parents=True, exist_ok=True)
            manifest, changed = build_site(
                settings, output, args.work_dir.resolve(), previous_site, source_repository, discovery_result
            )
        else:
            with tempfile.TemporaryDirectory(prefix="sndocs-") as temporary:
                manifest, changed = build_site(
                    settings, output, Path(temporary), previous_site, source_repository, discovery_result
                )
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"changed={'true' if changed else 'false'}\n")
                stream.write(f"latest={manifest['latest']}\n")
        print(json.dumps(manifest, indent=2))
        return 0
    if args.command == "package":
        files = package_site(args.site.resolve(), args.destination.resolve(), settings.archive_basename)
        manifest_target = args.destination.resolve() / MANIFEST_NAME
        shutil.copy2(args.site.resolve() / MANIFEST_NAME, manifest_target)
        print("\n".join(str(path) for path in [*files, manifest_target]))
        return 0
    if args.command == "validate":
        validate_site(args.site.resolve())
        print("site validation passed")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
