"""Normalize ServiceNowDocs Markdown without converting it to HTML.

Ported from the already-validated `normalize_markdown.py` at
`/home/dev/sndocs.com_testing/` (see that project's `plan_chatgpt.md` for the
full validation record). The normalizer separates safe, render-equivalent
cleanup from targeted repairs: it canonicalizes YAML front matter, cleans
redundant escapes and whitespace only when markdown-it-py renders the same
HTML, repairs broken HTML/pipe-table boundaries, converts only simple
rectangular HTML tables to pipe tables, and explicitly closes fences that
CommonMark otherwise closes at EOF.

Each file is checked against its own invariants (valid YAML front matter, no
broken table/fence boundaries, no open fences, stable H1 count, idempotence)
and any violation is recorded as an error rather than silently accepted.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import multiprocessing
import os
import platform
import re
import shutil
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable

import markdown_it
import yaml
from markdown_it import MarkdownIt

from sndocs.link_rewrite import rewrite_links

MARKDOWN_SUFFIXES = {".md", ".markdown"}
TABLE_RE = re.compile(r"<table(?P<attrs>[^>]*)>(?P<body>.*?)</table>", re.IGNORECASE | re.DOTALL)
ROW_RE = re.compile(r"<tr(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(
    r"<(?P<tag>th|td)(?P<attrs>[^>]*)>(?P<body>.*?)</(?:th|td)>",
    re.IGNORECASE | re.DOTALL,
)
BLOCK_IN_CELL_RE = re.compile(
    r"</?(?:table|caption|ul|ol|li|p|pre|div|h[1-6]|dl|dt|dd|blockquote|figure|details)\b",
    re.IGNORECASE,
)
MARKDOWN_BLOCK_IN_CELL_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+|^\s{0,3}#{1,6}\s+|^\s*(```|~~~)", re.MULTILINE)
FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")
ATTRIBUTE_RE = re.compile(r"(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)")

REPORT_FILENAME = "normalization-report.json"
MANIFEST_FILENAME = "normalization-manifest.json"

_source_root: Path
_output_root: Path
_parser: MarkdownIt
_known_paths: frozenset[str]


class NormalizationFailed(Exception):
    """Raised when one or more files failed their per-file invariants."""

    def __init__(self, report: dict[str, Any]):
        self.report = report
        failed = report["result"]["failed"]
        super().__init__(
            f"{failed} file(s) failed normalization invariants; "
            f"see {report['output']}/{REPORT_FILENAME}"
        )


def parser() -> MarkdownIt:
    return MarkdownIt(
        "commonmark",
        {"html": True, "linkify": False, "typographer": False},
    ).enable(["table", "strikethrough"])


def discover(source: Path) -> list[Path]:
    return sorted(
        (p.relative_to(source) for p in source.rglob("*") if p.is_file() and p.suffix.lower() in MARKDOWN_SUFFIXES),
        key=lambda p: p.as_posix(),
    )


def tolerant_front_matter(raw: str) -> dict[str, Any]:
    recovered: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, value = line.split(":", 1)
            if key.replace("_", "").replace("-", "").isalnum():
                current_key = key
                value = value.strip()
                if key == "breadcrumb" and value.startswith("[") and value.endswith("]"):
                    recovered[key] = [part.strip() for part in value[1:-1].split(",") if part.strip()]
                elif key == "reading_time_minutes" and value.isdigit():
                    recovered[key] = int(value)
                elif len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    try:
                        recovered[key] = yaml.safe_load(value)
                    except yaml.YAMLError:
                        recovered[key] = value[1:-1]
                else:
                    recovered[key] = value
                continue
        if current_key is not None and line[:1].isspace():
            recovered[current_key] = f"{recovered[current_key]}\n{line.strip()}"
    return recovered


def clean_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean_metadata_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_metadata_value(item) for item in value]
    if isinstance(value, tuple):
        return [clean_metadata_value(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\_", "_")
    return value


def split_front_matter(text: str) -> tuple[dict[str, Any] | None, str, bool]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text, False
    closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        return None, text, False
    raw = "".join(lines[1:closing])
    body = "".join(lines[closing + 1 :])
    fallback = False
    try:
        loaded = yaml.safe_load(raw)
        metadata = loaded if isinstance(loaded, dict) else {}
    except yaml.YAMLError:
        metadata = tolerant_front_matter(raw)
        fallback = True
    return clean_metadata_value(metadata), body, fallback


def dump_front_matter(metadata: dict[str, Any] | None) -> str:
    if metadata is None:
        return ""
    dumped = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=4096,
    ).rstrip()
    return f"---\n{dumped}\n---\n\n"


def fence_marker(line: str) -> tuple[str, int, str] | None:
    match = FENCE_RE.match(line.rstrip("\r\n"))
    if not match:
        return None
    fence = match.group("fence")
    return fence[0], len(fence), match.group("rest")


def split_fenced_segments(text: str) -> list[tuple[bool, str]]:
    """Return (is_fenced, text) chunks, including an unclosed final fence."""
    chunks: list[tuple[bool, str]] = []
    buffer: list[str] = []
    in_fence = False
    fence_char = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        marker = fence_marker(line)
        if not in_fence and marker and not (marker[0] == "`" and "`" in marker[2]):
            if buffer:
                chunks.append((False, "".join(buffer)))
                buffer = []
            in_fence = True
            fence_char, fence_length, _ = marker
            buffer.append(line)
        elif in_fence and marker and marker[0] == fence_char and marker[1] >= fence_length and not marker[2].strip():
            buffer.append(line)
            chunks.append((True, "".join(buffer)))
            buffer = []
            in_fence = False
        else:
            buffer.append(line)
    if buffer:
        chunks.append((in_fence, "".join(buffer)))
    return chunks


def unclosed_fence(text: str) -> tuple[str, int] | None:
    in_fence = False
    fence_char = ""
    fence_length = 0
    for line in text.splitlines():
        marker = fence_marker(line)
        if not in_fence and marker and not (marker[0] == "`" and "`" in marker[2]):
            in_fence = True
            fence_char, fence_length, _ = marker
        elif in_fence and marker and marker[0] == fence_char and marker[1] >= fence_length and not marker[2].strip():
            in_fence = False
    return (fence_char, fence_length) if in_fence else None


def transform_outside_fences(text: str, transform: Callable[[str], tuple[str, Counter[str]]]) -> tuple[str, Counter[str]]:
    output: list[str] = []
    stats: Counter[str] = Counter()
    for protected, chunk in split_fenced_segments(text):
        if protected:
            output.append(chunk)
        else:
            changed, chunk_stats = transform(chunk)
            output.append(changed)
            stats.update(chunk_stats)
    return "".join(output), stats


def cleanup_inline_segment(line: str) -> tuple[str, int]:
    output: list[str] = []
    cursor = 0
    replacements = 0
    while cursor < len(line):
        if line[cursor] == "`":
            run = 1
            while cursor + run < len(line) and line[cursor + run] == "`":
                run += 1
            end = line.find("`" * run, cursor + run)
            if end >= 0:
                output.append(line[cursor : end + run])
                cursor = end + run
                continue
        if line.startswith(r"\(", cursor) and (cursor == 0 or line[cursor - 1] != "]"):
            output.append("(")
            cursor += 2
            replacements += 1
            continue
        if line.startswith(r"\)", cursor):
            output.append(")")
            cursor += 2
            replacements += 1
            continue
        if line.startswith(r"\_", cursor):
            before = line[cursor - 1] if cursor else ""
            after = line[cursor + 2] if cursor + 2 < len(line) else ""
            if before.isalnum() and after.isalnum():
                output.append("_")
                cursor += 2
                replacements += 1
                continue
        output.append(line[cursor])
        cursor += 1
    return "".join(output), replacements


def cosmetic_candidate(text: str) -> tuple[str, Counter[str]]:
    stats: Counter[str] = Counter()
    output: list[str] = []
    in_table = False
    blank_run = 0
    for original_line in text.splitlines():
        lower = original_line.lower()
        if "<table" in lower:
            in_table = True
        line = original_line
        if not in_table and not line.startswith("    ") and not line.startswith("\t"):
            line, count = cleanup_inline_segment(line)
            stats["redundant_escapes_removed"] += count
            trailing = len(line) - len(line.rstrip(" "))
            if trailing == 1:
                line = line[:-1]
                stats["trailing_space_lines_cleaned"] += 1
            elif trailing > 2:
                line = line.rstrip(" ") + "  "
                stats["trailing_space_lines_cleaned"] += 1
        if not line:
            blank_run += 1
            if blank_run > 2:
                stats["excess_blank_lines_removed"] += 1
                if "</table>" in lower:
                    in_table = False
                continue
        else:
            blank_run = 0
        output.append(line)
        if "</table>" in lower:
            in_table = False
    return "\n".join(output).rstrip("\n") + "\n", stats


def table_attributes(raw: str) -> tuple[dict[str, str], bool]:
    attrs = {m.group("name").lower(): html.unescape(m.group("value")) for m in ATTRIBUTE_RE.finditer(raw)}
    residue = ATTRIBUTE_RE.sub("", raw).strip()
    allowed = set(attrs) <= {"id", "class"}
    return attrs, allowed and not residue


def normalize_cell(content: str) -> str:
    content = content.strip()
    content = re.sub(r"[ \t]*\r?\n[ \t]*", " ", content)
    content = re.sub(r" {2,}", " ", content)
    content = re.sub(r"(?<!\\)\|", r"\|", content)
    return content or " "


def convert_simple_tables(chunk: str, md: MarkdownIt) -> tuple[str, Counter[str]]:
    stats: Counter[str] = Counter()

    def replace(match: re.Match[str]) -> str:
        line_start = chunk.rfind("\n", 0, match.start()) + 1
        if chunk[line_start : match.start()].startswith(("    ", "\t")):
            return match.group(0)
        outer_attrs, attrs_ok = table_attributes(match.group("attrs"))
        if not attrs_ok:
            return match.group(0)

        rows: list[list[tuple[str, str]]] = []
        row_matches = list(ROW_RE.finditer(match.group("body")))
        outside_rows = ROW_RE.sub("", match.group("body"))
        outside_rows = re.sub(r"</?(?:thead|tbody|tfoot)\s*>", "", outside_rows, flags=re.IGNORECASE)
        outside_rows = re.sub(r"<col(?:group)?\b[^>]*>|</colgroup\s*>", "", outside_rows, flags=re.IGNORECASE)
        if outside_rows.strip():
            return match.group(0)
        for row_match in row_matches:
            if row_match.group("attrs").strip():
                return match.group(0)
            cells = list(CELL_RE.finditer(row_match.group("body")))
            if CELL_RE.sub("", row_match.group("body")).strip() or any(c.group("attrs").strip() for c in cells):
                return match.group(0)
            rows.append([(c.group("tag").lower(), c.group("body")) for c in cells])

        if (
            len(rows) < 2
            or not rows[0]
            or any(len(row) != len(rows[0]) for row in rows)
            or any(tag != "th" for tag, _ in rows[0])
            or any(tag != "td" for row in rows[1:] for tag, _ in row)
            or any(BLOCK_IN_CELL_RE.search(value) for row in rows for _, value in row)
            or any(MARKDOWN_BLOCK_IN_CELL_RE.search(value) for row in rows for _, value in row)
        ):
            return match.group(0)

        normalized_rows = [[normalize_cell(value) for _, value in row] for row in rows]
        table_lines = [
            "| " + " | ".join(normalized_rows[0]) + " |",
            "| " + " | ".join("---" for _ in normalized_rows[0]) + " |",
            *("| " + " | ".join(row) + " |" for row in normalized_rows[1:]),
        ]
        anchor = f'<a id="{html.escape(outer_attrs["id"], quote=True)}"></a>\n\n' if outer_attrs.get("id") else ""
        converted = anchor + "\n".join(table_lines)
        rendered = md.render(converted)
        if rendered.lower().count("<table") != 1:
            return match.group(0)
        stats["raw_tables_converted"] += 1
        if "class" in outer_attrs:
            stats["presentational_table_classes_dropped"] += 1
        return "\n\n" + converted + "\n\n"

    return TABLE_RE.sub(replace, chunk), stats


def repair_table_boundaries(chunk: str) -> tuple[str, Counter[str]]:
    repaired, pipe_count = re.subn(r"</table>[ \t]*\|", "</table>\n\n|", chunk, flags=re.IGNORECASE)
    repaired, fence_count = re.subn(r"</table>[ \t]*(?=`{3,}|~{3,})", "</table>\n\n", repaired, flags=re.IGNORECASE)
    return repaired, Counter(
        {
            "table_pipe_boundaries_repaired": pipe_count,
            "table_fence_boundaries_repaired": fence_count,
        }
    )


def count_remaining_tables(chunk: str) -> tuple[str, Counter[str]]:
    return chunk, Counter({"raw_tables_remaining": len(TABLE_RE.findall(chunk))})


def close_unclosed_fence(text: str) -> tuple[str, Counter[str]]:
    marker = unclosed_fence(text)
    if marker is None:
        return text, Counter()
    closing = marker[0] * marker[1]
    candidate = text.rstrip("\n") + f"\n{closing}\n"
    return candidate, Counter({"unclosed_fences_closed_at_eof": 1})


def h1_count(md: MarkdownIt, body: str) -> int:
    return sum(token.type == "heading_open" and token.tag == "h1" for token in md.parse(body))


def normalize_text(
    text: str,
    md: MarkdownIt,
    relative_path: str,
    known_paths: frozenset[str],
    *,
    audit_idempotence: bool = True,
) -> tuple[str, Counter[str], list[str]]:
    stats: Counter[str] = Counter()
    errors: list[str] = []
    if text.startswith("﻿"):
        text = text[1:]
        stats["byte_order_marks_removed"] += 1
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    metadata, body, fallback = split_front_matter(text)
    leading_newlines = len(body) - len(body.lstrip("\n"))
    if leading_newlines:
        body = body.lstrip("\n")
        stats["leading_blank_lines_removed"] += leading_newlines
    if fallback:
        stats["front_matter_fallbacks"] += 1
    if metadata is not None:
        stats["front_matter_canonicalized"] += 1

    body, link_stats = transform_outside_fences(
        body, lambda chunk: rewrite_links(chunk, known_paths, relative_path)
    )
    stats.update(link_stats)

    before_h1 = h1_count(md, body)
    cosmetic, cosmetic_stats = cosmetic_candidate(body)
    if cosmetic != body:
        if md.render(cosmetic).rstrip("\n") == md.render(body).rstrip("\n"):
            body = cosmetic
            stats.update(cosmetic_stats)
            stats["files_with_render_equivalent_cleanup"] += 1
        else:
            stats["render_changing_cleanup_rejected"] += 1

    for _ in range(5):
        structural_before = body
        body, boundary_stats = transform_outside_fences(body, repair_table_boundaries)
        stats.update(boundary_stats)
        body, table_stats = transform_outside_fences(body, lambda chunk: convert_simple_tables(chunk, md))
        stats.update(table_stats)
        if body == structural_before:
            break
    else:
        errors.append("structural normalization did not converge")
    body, fence_stats = close_unclosed_fence(body)
    stats.update(fence_stats)
    final_cosmetic, final_cosmetic_stats = cosmetic_candidate(body)
    if final_cosmetic != body and md.render(final_cosmetic).rstrip("\n") == md.render(body).rstrip("\n"):
        body = final_cosmetic
        stats.update(final_cosmetic_stats)
    body = body.rstrip("\n") + "\n" if body else ""
    _, remaining_table_stats = transform_outside_fences(body, count_remaining_tables)
    stats.update(remaining_table_stats)

    normalized = dump_front_matter(metadata) + body
    if metadata is not None:
        try:
            parsed = yaml.safe_load(normalized.split("---\n", 2)[1])
            if not isinstance(parsed, dict):
                errors.append("normalized front matter is not a mapping")
        except yaml.YAMLError as exc:
            errors.append(f"normalized front matter is invalid YAML: {exc}")
    _, remaining_boundary_stats = transform_outside_fences(body, repair_table_boundaries)
    if sum(remaining_boundary_stats.values()):
        errors.append("broken table boundary remains outside a code fence")
    if unclosed_fence(body) is not None:
        errors.append("unclosed fence remains")
    if h1_count(md, body) != before_h1:
        errors.append("H1 token count changed")
    if audit_idempotence:
        second, _, second_errors = normalize_text(
            normalized, md, relative_path, known_paths, audit_idempotence=False
        )
        if second != normalized:
            errors.append("normalization is not idempotent")
        errors.extend(f"second pass: {error}" for error in second_errors)
    return normalized, stats, errors


def _normalize_one(
    relative: Path, source_root: Path, output_root: Path, md: MarkdownIt, known_paths: frozenset[str]
) -> dict[str, Any]:
    source_path = source_root / relative
    output_path = output_root / relative
    try:
        original = source_path.read_text(encoding="utf-8")
        normalized, stats, errors = normalize_text(original, md, relative.as_posix(), known_paths)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(normalized, encoding="utf-8")
        return {
            "path": relative.as_posix(),
            "changed": normalized != original,
            "input_bytes": len(original.encode("utf-8")),
            "output_bytes": len(normalized.encode("utf-8")),
            "stats": dict(stats),
            "errors": errors,
        }
    except Exception as exc:
        return {
            "path": relative.as_posix(),
            "changed": False,
            "input_bytes": 0,
            "output_bytes": 0,
            "stats": {},
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _init_worker(source: str, output: str, known_paths: list[str]) -> None:
    global _source_root, _output_root, _parser, _known_paths
    _source_root = Path(source)
    _output_root = Path(output)
    _parser = parser()
    _known_paths = frozenset(known_paths)


def _normalize_one_worker(relative_text: str) -> dict[str, Any]:
    return _normalize_one(Path(relative_text), _source_root, _output_root, _parser, _known_paths)


def normalize_corpus(source: Path, output: Path, workers: int | None = None) -> dict[str, Any]:
    """Normalize every Markdown file under `source` into `output`, mirroring the
    source's relative directory structure. Always writes a report and a manifest
    into `output`. Raises `NormalizationFailed` if any file failed its invariants;
    raises `FileNotFoundError` if `source` does not exist."""
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source does not exist: {source}")
    workers = workers if workers is not None else max(1, os.cpu_count() or 1)
    if workers < 1:
        raise ValueError("workers must be at least 1")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    discovery_started = time.perf_counter()
    paths = discover(source)
    known_paths = frozenset(p.as_posix() for p in paths)
    discovery_seconds = time.perf_counter() - discovery_started

    started = time.perf_counter()
    if workers == 1 or len(paths) <= 1:
        md = parser()
        results = [_normalize_one(p, source, output, md, known_paths) for p in paths]
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("fork"),
            initializer=_init_worker,
            initargs=(str(source), str(output), sorted(known_paths)),
        ) as executor:
            results = list(executor.map(_normalize_one_worker, (p.as_posix() for p in paths), chunksize=16))
    elapsed = time.perf_counter() - started

    aggregate: Counter[str] = Counter()
    for result in results:
        aggregate.update(result["stats"])
    failures = [{"path": r["path"], "errors": r["errors"]} for r in results if r["errors"]]

    report = {
        "source": str(source),
        "output": str(output),
        "environment": {
            "python": platform.python_version(),
            "markdown_it_py": markdown_it.__version__,
            "pyyaml": yaml.__version__,
            "workers": workers,
        },
        "benchmark": {
            "discovery_seconds": discovery_seconds,
            "normalization_wall_seconds": elapsed,
            "files_per_second": (len(paths) / elapsed) if elapsed else 0.0,
            "input_bytes": sum(r["input_bytes"] for r in results),
            "output_bytes": sum(r["output_bytes"] for r in results),
        },
        "result": {
            "total_files": len(results),
            "succeeded": len(results) - len(failures),
            "failed": len(failures),
            "changed_files": sum(r["changed"] for r in results),
            "transformations": dict(sorted(aggregate.items())),
            "failures": failures,
        },
    }
    (output / REPORT_FILENAME).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    manifest = {"source": str(source), "output": str(output), "files": results}
    (output / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if failures:
        raise NormalizationFailed(report)
    return report
