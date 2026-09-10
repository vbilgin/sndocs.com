"""Seam 2 for the v1.2 CLI output work (parent #45): the `Reporter` abstraction
exercised directly with an injected `rich.Console` backed by a `StringIO`, with
`force_terminal` set both ways. Assertions are on what a user or a script sees —
`5/5`, `100%`, `WARNING:`, `ERROR:`, a heading — never on control characters,
frame counts, or bar glyphs.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from rich.console import Console

from sndocs.reporter import Reporter, Verbosity

SRC = Path(__file__).resolve().parent.parent / "src" / "sndocs"


def buffered_console(*, force_terminal: bool, no_color: bool = True) -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return (
        Console(file=buffer, force_terminal=force_terminal, no_color=no_color, width=100),
        buffer,
    )


def make_reporter(
    verbosity: Verbosity = Verbosity.normal,
    *,
    force_terminal: bool = True,
    no_color: bool = True,
    out_console: Console | None = None,
    plain_progress_interval: float = 0.0,
) -> tuple[Reporter, io.StringIO]:
    console, buffer = buffered_console(force_terminal=force_terminal, no_color=no_color)
    reporter = Reporter(
        console,
        verbosity,
        out_console=out_console,
        plain_progress_interval=plain_progress_interval,
    )
    return reporter, buffer


# -- determinate progress --------------------------------------------------


def test_determinate_progress_reaches_full_total_on_a_terminal() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=True)

    with reporter.progress("Normalizing", total=5) as tick:
        for _ in range(5):
            tick()

    output = buffer.getvalue()
    assert "5/5" in output
    assert "100%" in output
    assert reporter.uses_progress_bar is True


def test_determinate_progress_uses_the_plain_path_off_a_terminal() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=False)

    with reporter.progress("Normalizing", total=5) as tick:
        for _ in range(5):
            tick()

    output = buffer.getvalue()
    assert "Normalizing: 5/5 (100%)" in output
    assert "\x1b[" not in output  # no ANSI redraw sequences in a captured log
    assert reporter.uses_progress_bar is False


def test_verbose_progress_prints_one_line_per_item_instead_of_a_bar() -> None:
    reporter, buffer = make_reporter(Verbosity.verbose, force_terminal=True)

    with reporter.progress("Normalizing", total=3) as tick:
        tick("alpha.md")
        tick("beta.md")
        tick("gamma.md")

    output = buffer.getvalue()
    assert "alpha.md" in output
    assert "beta.md" in output
    assert "[3/3]" in output
    assert reporter.uses_progress_bar is False
    assert reporter.shows_subprocess_output is True


def test_quiet_progress_emits_nothing() -> None:
    reporter, buffer = make_reporter(Verbosity.quiet, force_terminal=True)

    with reporter.progress("Normalizing", total=4) as tick:
        for _ in range(4):
            tick("ignored.md")

    assert buffer.getvalue() == ""
    assert reporter.shows_subprocess_output is False


def test_normal_on_a_terminal_uses_a_bar_and_hides_subprocess_output() -> None:
    reporter, _ = make_reporter(Verbosity.normal, force_terminal=True)

    assert reporter.uses_progress_bar is True
    assert reporter.shows_subprocess_output is False


def test_force_terminal_false_selects_the_plain_path_even_with_colour_forced() -> None:
    # `--color=always` semantics: colour is on (no_color=False), but stderr is
    # not a terminal — the plain, non-animated path must still win.
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=False, no_color=False)

    with reporter.progress("Building", total=2) as tick:
        tick()
        tick()

    assert reporter.uses_progress_bar is False
    assert "Building: 2/2 (100%)" in buffer.getvalue()


# -- spinner ---------------------------------------------------------------


def test_spinner_prints_label_and_elapsed_on_the_plain_path() -> None:
    reporter, buffer = make_reporter(Verbosity.verbose, force_terminal=True)

    with reporter.spinner("Fetching corpus"):
        pass

    output = buffer.getvalue()
    assert "Fetching corpus..." in output
    assert re.search(r"Fetching corpus: done \(\d+\.\d+s\)", output)


def test_spinner_on_a_terminal_shows_the_label_and_does_not_raise() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=True)

    with reporter.spinner("Rendering site"):
        pass

    assert "Rendering site" in buffer.getvalue()


def test_quiet_spinner_emits_nothing() -> None:
    reporter, buffer = make_reporter(Verbosity.quiet, force_terminal=True)

    with reporter.spinner("Fetching corpus"):
        pass

    assert buffer.getvalue() == ""


# -- warnings ------------------------------------------------------------


def test_warn_groups_messages_and_does_not_stream_them_at_normal() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=False)

    reporter.warn("stranded delimiter row in prose")
    reporter.warn("residual escape inside a raw HTML table")
    assert buffer.getvalue() == ""  # held back until the flush

    reporter.flush_warnings()

    output = buffer.getvalue()
    assert "Warnings:" in output
    assert "stranded delimiter row in prose" in output
    assert "residual escape inside a raw HTML table" in output


def test_warn_holds_messages_until_flush_at_verbose_too() -> None:
    reporter, buffer = make_reporter(Verbosity.verbose, force_terminal=False)

    reporter.warn("first")
    reporter.warn("second")
    assert buffer.getvalue() == ""  # grouped, not streamed, at every level

    reporter.flush_warnings()

    output = buffer.getvalue()
    assert "first" in output
    assert "second" in output


def test_quiet_suppresses_warnings_entirely() -> None:
    reporter, buffer = make_reporter(Verbosity.quiet, force_terminal=False)

    reporter.warn("should not appear")
    reporter.flush_warnings()

    assert buffer.getvalue() == ""


def test_flush_warnings_is_a_noop_with_nothing_pending() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=False)

    reporter.flush_warnings()

    assert buffer.getvalue() == ""


# -- fatal error -------------------------------------------------------------


def test_error_renders_heading_message_and_optional_pointer() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=False)

    reporter.error(
        "Normalization failed",
        "3 files could not be parsed",
        report_path="/tmp/normalization-report.json",
    )

    output = buffer.getvalue()
    assert "ERROR: Normalization failed" in output
    assert "3 files could not be parsed" in output
    assert "See /tmp/normalization-report.json" in output


def test_error_without_a_pointer_omits_the_see_line() -> None:
    reporter, buffer = make_reporter(Verbosity.normal, force_terminal=False)

    reporter.error("Bind failed", "address already in use")

    output = buffer.getvalue()
    assert "ERROR: Bind failed" in output
    assert "address already in use" in output
    assert "See " not in output


def test_error_is_emitted_even_when_quiet() -> None:
    reporter, buffer = make_reporter(Verbosity.quiet, force_terminal=False)

    reporter.error("Fetch failed", "network unreachable")

    assert "ERROR: Fetch failed" in buffer.getvalue()


# -- debug traceback -------------------------------------------------------


def test_debug_prints_a_formatted_traceback_for_an_exception() -> None:
    reporter, buffer = make_reporter(Verbosity.debug, force_terminal=True)

    try:
        raise ValueError("boom")
    except ValueError as exc:
        reporter.print_exception(exc)

    output = buffer.getvalue()
    assert "Traceback" in output
    assert "ValueError" in output
    assert "boom" in output


def test_traceback_is_suppressed_below_debug() -> None:
    reporter, buffer = make_reporter(Verbosity.verbose, force_terminal=True)

    try:
        raise ValueError("boom")
    except ValueError as exc:
        reporter.print_exception(exc)

    assert buffer.getvalue() == ""


# -- retained summary line -----------------------------------------------


def test_summary_goes_to_the_out_console_verbatim() -> None:
    out_console, out = buffered_console(force_terminal=False)
    reporter, err = make_reporter(Verbosity.normal, force_terminal=False, out_console=out_console)

    reporter.summary("normalize: 5/5 files normalized into .sndocs/normalized (2 changed)")

    assert "normalize: 5/5 files normalized into .sndocs/normalized (2 changed)" in out.getvalue()
    assert err.getvalue() == ""


def test_summary_is_suppressed_when_quiet() -> None:
    reporter, buffer = make_reporter(Verbosity.quiet, force_terminal=False)

    reporter.summary("build: rendered .sndocs/normalized into .sndocs/site")

    assert buffer.getvalue() == ""


# -- acceptance-criteria guards ------------------------------------------


def test_only_reporter_imports_rich() -> None:
    offenders = [
        path.name
        for path in SRC.glob("*.py")
        if path.name != "reporter.py"
        and re.search(r"^\s*(import rich\b|from rich\b)", path.read_text(), re.MULTILINE)
    ]
    assert offenders == []


def test_cli_does_not_import_reporter_yet() -> None:
    imports_reporter = re.search(
        r"^\s*(from sndocs\.reporter\b|from \.reporter\b|import sndocs\.reporter\b"
        r"|from sndocs import [^\n]*\breporter\b)",
        (SRC / "cli.py").read_text(),
        re.MULTILINE,
    )
    assert imports_reporter is None
