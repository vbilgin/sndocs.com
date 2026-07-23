from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .artifacts import package_site, validate_site
from .builder import MANIFEST_NAME, build_site, plan_build
from .config import load_settings
from .discovery import discover
from .quality import STATUSES, load_quality_ruleset
from .source import LocalSource, RemoteSource, clone_local_source, update_local_source
from .ui_audit import _audit_paths_overlap, audit_site_ui


class _Formatter(argparse.RawDescriptionHelpFormatter):
    pass


def _common_options(command: argparse.ArgumentParser, *, suppress_defaults: bool = True) -> None:
    default = argparse.SUPPRESS if suppress_defaults else Path("pipeline.toml")
    command.add_argument(
        "--config",
        type=Path,
        default=default,
        help="pipeline configuration file (default: pipeline.toml)",
    )
    json_default = argparse.SUPPRESS if suppress_defaults else False
    command.add_argument(
        "--json",
        action="store_true",
        default=json_default,
        help="write one machine-readable result object to stdout",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="sndocs",
        description="Build the sndocs.com static documentation mirror",
        formatter_class=_Formatter,
    )
    _common_options(result, suppress_defaults=False)
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = result.add_subparsers(dest="command", required=True)

    source = commands.add_parser(
        "source",
        help="manage and verify a reusable upstream clone",
        description="Clone, update, or check a reusable upstream repository.",
        formatter_class=_Formatter,
        epilog="Examples:\n  sndocs source clone ../ServiceNowDocs\n  sndocs source check ../ServiceNowDocs",
    )
    _common_options(source)
    source_commands = source.add_subparsers(dest="source_command", required=True)
    for name, help_text in (
        ("clone", "create and verify a new full upstream clone"),
        ("update", "fetch, prune, and verify an existing clone"),
        ("check", "verify an existing clone without network access"),
    ):
        subcommand = source_commands.add_parser(
            name,
            help=help_text,
            description=help_text,
            formatter_class=_Formatter,
            epilog=f"Example:\n  sndocs source {name} ../ServiceNowDocs",
        )
        _common_options(subcommand)
        subcommand.add_argument("path", type=Path, help="path to the reusable upstream clone")

    discover_command = commands.add_parser(
        "discover",
        help="discover upstream families and publication metadata",
        description="Discover families, publications, and exact branch SHAs without building.",
        formatter_class=_Formatter,
        epilog="Examples:\n  sndocs discover\n  sndocs discover --source ../ServiceNowDocs --json",
    )
    _common_options(discover_command)
    discover_command.add_argument(
        "--source", type=Path, help="use this clean local clone offline instead of GitHub"
    )

    build = commands.add_parser(
        "build",
        help="build, plan, or incrementally assemble the site",
        description=(
            "Build the selected site. Existing output is refused unless --clean is supplied.\n"
            "With --dry-run, discovery and reuse decisions are reported without writing output."
        ),
        formatter_class=_Formatter,
        epilog=(
            "Examples:\n"
            "  sndocs build --output site --source ../ServiceNowDocs\n"
            "  sndocs build --dry-run --reuse-from previous-site --json"
        ),
    )
    _common_options(build)
    build.add_argument("--output", type=Path, help="generated site directory (required unless --dry-run)")
    build.add_argument("--clean", action="store_true", help="remove an existing output directory before building")
    build.add_argument("--work-dir", type=Path, help="preserve intermediate build files at this path")
    build.add_argument("--reuse-from", type=Path, help="reuse unchanged families and retain archives from this site")
    build.add_argument("--source", type=Path, help="use this clean local clone offline instead of GitHub")
    build.add_argument(
        "--family",
        action="append",
        default=[],
        metavar="NAME",
        help="build this family; repeat to select several in upstream order",
    )
    build.add_argument("--smoke", action="store_true", help="build one family without search indexing")
    build.add_argument(
        "--dry-run",
        action="store_true",
        help="report rebuild, reuse, and archive actions without writing files",
    )

    package = commands.add_parser(
        "package",
        help="validate and package a production site",
        epilog="Example:\n  sndocs package --site site --destination artifacts",
        formatter_class=_Formatter,
    )
    _common_options(package)
    package.add_argument("--site", type=Path, required=True, help="assembled production site")
    package.add_argument("--destination", type=Path, required=True, help="archive output directory")

    validate = commands.add_parser(
        "validate",
        help="validate an assembled site",
        epilog="Example:\n  sndocs validate --site site",
        formatter_class=_Formatter,
    )
    _common_options(validate)
    validate.add_argument("--site", type=Path, default=Path("site"), help="site to validate (default: site)")

    audit_ui = commands.add_parser(
        "audit-ui",
        help="find structural and rendered UI defects in a built site",
        description="Scan every HTML page and render high-risk pages plus a deterministic sample.",
        epilog="Example:\n  sndocs audit-ui --site site --output ui-report",
        formatter_class=_Formatter,
    )
    _common_options(audit_ui)
    audit_ui.add_argument("--site", type=Path, required=True, help="assembled production or smoke site")
    audit_ui.add_argument("--output", type=Path, required=True, help="HTML, JSON, and screenshot report directory")
    audit_ui.add_argument("--clean", action="store_true", help="remove an existing report directory")
    audit_ui.add_argument("--sample-size", type=int, default=100, help="additional pages to render (default: 100)")
    audit_ui.add_argument("--seed", type=int, default=0, help="deterministic sampling seed (default: 0)")

    quality = commands.add_parser(
        "quality",
        help="inspect and validate the packaged site-quality rules",
        description="Validate, list, or show the human-readable site-quality ruleset.",
        formatter_class=_Formatter,
    )
    _common_options(quality)
    quality_commands = quality.add_subparsers(dest="quality_command", required=True)
    quality_validate = quality_commands.add_parser(
        "validate", help="validate rules and detector registration"
    )
    _common_options(quality_validate)
    quality_list = quality_commands.add_parser("list", help="list quality rules")
    _common_options(quality_list)
    quality_list.add_argument("--status", choices=sorted(STATUSES), help="filter by lifecycle status")
    quality_list.add_argument("--category", help="filter by ruleset category")
    quality_show = quality_commands.add_parser("show", help="show one complete quality rule")
    _common_options(quality_show)
    quality_show.add_argument("rule_id", help="stable rule identifier, for example SND-NAV-001")

    serve = commands.add_parser(
        "serve",
        help="preview a built site with clean directory URLs",
        description="Serve a completed site locally. Use --port 0 to select an available port.",
        epilog="Example:\n  sndocs serve --site site --port 8000",
        formatter_class=_Formatter,
    )
    serve.add_argument("--config", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    serve.add_argument("--site", type=Path, default=Path("site"), help="site to serve (default: site)")
    serve.add_argument("--bind", default="127.0.0.1", help="address to bind (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="port to bind; 0 selects an available port (default: 8000)")
    return result


def _emit(args: argparse.Namespace, result: dict, summary: str) -> None:
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(summary)


def _selected_families(args: argparse.Namespace) -> tuple[str, ...] | None:
    families = args.family
    if len(families) != len(set(families)):
        duplicates = sorted({family for family in families if families.count(family) > 1})
        raise ValueError(f"duplicate release families: {', '.join(duplicates)}")
    if args.smoke and len(families) > 1:
        raise ValueError("--smoke accepts at most one --family")
    return tuple(families) if families else None


def _local_source(path: Path | None, settings):
    return LocalSource(path, settings) if path else RemoteSource()


def _source_result(path: Path, settings, source) -> dict:
    discovery_result = discover(settings, source)
    return {
        "source": str(path.resolve()),
        "repository": settings.repository,
        "families": discovery_result.families,
        "status": "ok",
    }


def _write_github_output(changed: bool, latest: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as stream:
        stream.write(f"changed={'true' if changed else 'false'}\n")
        stream.write(f"latest={latest}\n")


def _run(args: argparse.Namespace, argument_parser: argparse.ArgumentParser) -> int:
    if args.command == "serve" and getattr(args, "json", False):
        argument_parser.error("--json is not supported by serve")
    if args.command == "quality":
        ruleset = load_quality_ruleset()
        if args.quality_command == "validate":
            result = {
                "valid": True,
                "name": ruleset.name,
                "schema_version": ruleset.schema_version,
                "digest": ruleset.digest,
                "rules": len(ruleset.rules),
                "detectors": len(ruleset.detectors),
            }
            _emit(
                args,
                result,
                f"Quality ruleset passed: {len(ruleset.rules)} rules, "
                f"{len(ruleset.detectors)} detectors",
            )
            return 0
        if args.quality_command == "list":
            if args.category and args.category not in ruleset.categories:
                argument_parser.error(
                    f"unknown quality category: {args.category}; "
                    f"choose from {', '.join(ruleset.categories)}"
                )
            rules = [
                rule
                for rule in sorted(ruleset.rules.values(), key=lambda item: item.id)
                if (not args.status or rule.status == args.status)
                and (not args.category or rule.category == args.category)
            ]
            if args.json:
                print(json.dumps({"rules": [rule.summary() for rule in rules]}, indent=2))
            else:
                print(
                    "\n".join(
                        f"{rule.id}  {rule.status:<10} {rule.category:<13} "
                        f"{rule.severity:<7} {rule.assessment:<9} {rule.title}"
                        for rule in rules
                    )
                )
            return 0
        rule = ruleset.rules.get(args.rule_id)
        if rule is None:
            argument_parser.error(f"unknown quality rule: {args.rule_id}")
        if args.json:
            print(json.dumps(rule.to_dict(include_body=True), indent=2))
        else:
            print(rule.source, end="")
        return 0
    settings = load_settings(args.config.resolve())

    if args.command == "source":
        path = args.path.resolve()
        if args.source_command == "clone":
            source = clone_local_source(path, settings)
        elif args.source_command == "update":
            source = update_local_source(path, settings)
        else:
            source = LocalSource(path, settings)
        result = _source_result(path, settings, source)
        _emit(args, result, f"Source {args.source_command} passed: {path} ({len(result['families'])} families)")
        return 0

    if args.command == "discover":
        discovery_result = discover(settings, _local_source(args.source, settings))
        result = discovery_result.to_dict()
        _emit(args, result, f"Discovered {len(result['families'])} families; latest is {result['latest']}")
        return 0

    if args.command == "build":
        if args.dry_run and args.clean:
            argument_parser.error("--clean cannot be used with --dry-run")
        if not args.dry_run and args.output is None:
            argument_parser.error("--output is required unless --dry-run is supplied")
        output = args.output.resolve() if args.output else None
        reuse_from = args.reuse_from.resolve() if args.reuse_from else None
        if output and reuse_from and output == reuse_from:
            argument_parser.error("--reuse-from must be different from --output")
        if output and output.exists() and not args.dry_run and not args.clean:
            argument_parser.error(f"output already exists: {output}; pass --clean to replace it")
        allowlist = _selected_families(args)
        source_repository = _local_source(args.source, settings)
        discovery_result = discover(settings, source_repository, allowlist)
        build_profile = "smoke" if args.smoke else "production"
        if args.smoke and not allowlist:
            latest = discovery_result.latest
            discovery_result.families = [latest]
            discovery_result.shas = {latest: discovery_result.shas[latest]}
        plan = plan_build(settings, reuse_from, discovery_result, build_profile=build_profile)
        if args.dry_run:
            result = {
                "latest": plan["latest"],
                "build_profile": build_profile,
                "families": discovery_result.families,
                "actions": plan["actions"],
            }
            summary = "\n".join(
                f"{item['family']}: {item['action']} — {item['reason']}" for item in plan["actions"]
            )
            _emit(args, result, summary)
            return 0
        assert output is not None
        if output.exists():
            shutil.rmtree(output)
        if args.work_dir:
            args.work_dir.mkdir(parents=True, exist_ok=True)
            manifest, changed = build_site(
                settings,
                output,
                args.work_dir.resolve(),
                reuse_from,
                source_repository,
                discovery_result,
                build_profile=build_profile,
            )
        else:
            temporary_root = Path.cwd() / ".temp"
            temporary_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="sndocs-", dir=temporary_root) as temporary:
                print(f"Automatic workspace: {temporary}", file=sys.stderr)
                manifest, changed = build_site(
                    settings,
                    output,
                    Path(temporary),
                    reuse_from,
                    source_repository,
                    discovery_result,
                    build_profile=build_profile,
                    cleanup_work=True,
                )
                print(f"Automatic workspace removed: {temporary}", file=sys.stderr)
        _write_github_output(changed, manifest["latest"])
        result = {
            "changed": changed,
            "latest": manifest["latest"],
            "build_profile": manifest["build_profile"],
            "families": list(manifest["families"]),
            "output": str(output),
            "manifest": str(output / MANIFEST_NAME),
        }
        _emit(args, result, f"Built {len(result['families'])} families at {output}; changed={str(changed).lower()}")
        return 0

    if args.command == "package":
        site = args.site.resolve()
        destination = args.destination.resolve()
        files = package_site(site, destination, settings.archive_basename)
        manifest_target = destination / MANIFEST_NAME
        shutil.copy2(site / MANIFEST_NAME, manifest_target)
        generated = [*files, manifest_target]
        result = {"site": str(site), "destination": str(destination), "files": [str(path) for path in generated]}
        _emit(args, result, f"Packaged {len(generated)} files in {destination}")
        return 0

    if args.command == "validate":
        site = args.site.resolve()
        validate_site(site)
        _emit(args, {"site": str(site), "valid": True}, f"Site validation passed: {site}")
        return 0

    if args.command == "audit-ui":
        site = args.site.resolve()
        output = args.output.resolve()
        if _audit_paths_overlap(site, output):
            argument_parser.error("--output must not overlap --site")
        if output.exists() and not args.clean:
            argument_parser.error(f"output already exists: {output}; pass --clean to replace it")
        if output.exists():
            shutil.rmtree(output)
        report = audit_site_ui(
            site, output, sample_size=args.sample_size, seed=args.seed
        )
        result = {
            "site": str(site),
            "output": str(output),
            "findings": len(report["findings"]),
            "errors": len(report["errors"]),
            "coverage": report["coverage"],
        }
        _emit(
            args,
            result,
            f"UI audit found {result['findings']} findings; report: {output / 'index.html'}",
        )
        return 0

    if args.command == "serve":
        site = args.site.resolve()
        if not site.is_dir():
            argument_parser.error(f"site directory does not exist: {site}; build it first or pass --site PATH")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
        server = http.server.ThreadingHTTPServer((args.bind, args.port), handler)
        host, port = server.server_address[:2]
        display_host = args.bind if args.bind else host
        print(f"Previewing {site} at http://{display_host}:{port}/")
        print("Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nPreview stopped.")
        finally:
            server.server_close()
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    try:
        return _run(args, argument_parser)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        argument_parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
