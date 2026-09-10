"""The shared CLI output layer.

Every `sndocs` command routes its progress bars, spinners, warnings, and error
blocks through the single `Reporter` abstraction defined here, so that terminal
vs CI, `--quiet`, and `--verbose` behaviour is decided in one place instead of
being sprinkled across the five commands (parent issue #45, user story 31).
`Reporter` wraps a `rich.Console` for diagnostics and progress (stderr), an
optional second `rich.Console` for the retained one-line command summaries
(stdout), and a resolved `Verbosity`.

**This module is the only importer of `rich` in the codebase** — see ADR 0004;
`tests/test_reporter.py::test_only_reporter_imports_rich` enforces it.

At the ticket that introduced this module (#46) no command wires it in yet
(`test_cli_does_not_import_reporter_yet`); the per-command adoption lands in the
follow-up tickets under #45.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import IntEnum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.traceback import Traceback

# In non-terminal mode a redrawing bar is meaningless in a captured log, so the
# determinate-progress path emits one plain `done/total` line at most this often
# (plus a guaranteed final one). The CLI can pass its own interval; tests pass 0
# to see every tick.
PLAIN_PROGRESS_INTERVAL_SECONDS = 2.0

# The callable a `progress()` context yields: call it once per finished item to
# advance the bar / emit the next line. The optional argument is the item label,
# shown only on the per-item `verbose` path.
Tick = Callable[..., None]


class Verbosity(IntEnum):
    """Resolved output level for a `sndocs` run.

    Ordered so `>=` / `<=` comparisons gate behaviour:

    * ``quiet`` — only error blocks are emitted.
    * ``normal`` — live bar / spinner on a terminal, plain periodic lines off
      one; subprocess output (git, MkDocs, Pagefind) hidden.
    * ``verbose`` — per-item log lines instead of a bar; subprocess output shown.
    * ``debug`` — as ``verbose`` plus a formatted traceback on failure.

    Mapping the raw ``-v`` count and ``-q`` flag onto this enum belongs with the
    global CLI flags themselves — the next ticket under #45 (see ADR 0004
    follow-ups).
    """

    quiet = 0
    normal = 1
    verbose = 2
    debug = 3


class Reporter:
    """Progress and diagnostics for one `sndocs` run.

    Construct with an explicit `rich.Console` so tests can back it with a
    `StringIO` and pick `force_terminal` either way. `out_console` is where the
    retained summary lines go (stdout); it defaults to `console` for the common
    single-stream test case, and the CLI passes a real stdout `Console`.
    """

    def __init__(
        self,
        console: Console,
        verbosity: Verbosity = Verbosity.normal,
        *,
        out_console: Console | None = None,
        plain_progress_interval: float = PLAIN_PROGRESS_INTERVAL_SECONDS,
    ) -> None:
        self.console = console
        self.verbosity = verbosity
        self.out_console = out_console if out_console is not None else console
        self.plain_progress_interval = plain_progress_interval
        self._warnings: list[str] = []

    # -- capability queries the commands branch on --------------------------

    @property
    def uses_progress_bar(self) -> bool:
        """True when a live redrawing bar is the right choice: ``normal``
        verbosity on a real terminal. ``quiet`` shows nothing, ``verbose`` /
        ``debug`` show per-item lines, and a non-terminal gets plain lines."""
        return self.verbosity is Verbosity.normal and self.console.is_terminal

    @property
    def shows_subprocess_output(self) -> bool:
        """True from ``verbose`` up: let git / MkDocs / Pagefind output through
        instead of swallowing it."""
        return self.verbosity >= Verbosity.verbose

    # -- determinate progress ---------------------------------------------------

    @contextmanager
    def progress(self, description: str, total: int) -> Iterator[Tick]:
        """Determinate progress over a known `total`. Yields a `Tick` — call it
        once per finished item. At ``normal`` on a terminal this is a live bar
        with count, percentage, elapsed and ETA columns; off a terminal it is a
        throttled plain ``done/total`` line with a guaranteed final ``total/total
        (100%)``; at ``verbose`` / ``debug`` it is one line per item; at
        ``quiet`` it is silent."""
        if self.verbosity is Verbosity.quiet:
            yield _noop_tick
            return

        if self.verbosity >= Verbosity.verbose:
            yield from self._verbose_progress(description, total)
            return

        if not self.console.is_terminal:
            yield from self._plain_progress(description, total)
            return

        yield from self._bar_progress(description, total)

    def _verbose_progress(self, description: str, total: int) -> Iterator[Tick]:
        done = 0

        def tick(item: str | None = None) -> None:
            nonlocal done
            done += 1
            suffix = f"  {item}" if item else ""
            self._print(f"{description} [{done}/{total}]{suffix}")

        yield tick

    def _plain_progress(self, description: str, total: int) -> Iterator[Tick]:
        done = 0
        last = 0.0

        def emit() -> None:
            shown = min(done, total) if total else done
            pct = 100 if total == 0 else round(shown * 100 / total)
            self._print(f"{description}: {shown}/{total} ({pct}%)")

        def tick(item: str | None = None) -> None:
            nonlocal done, last
            done += 1
            now = time.monotonic()
            if now - last >= self.plain_progress_interval:
                last = now
                emit()

        try:
            yield tick
        finally:
            emit()

    def _bar_progress(self, description: str, total: int) -> Iterator[Tick]:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            auto_refresh=False,
        ) as bar:
            task = bar.add_task(description, total=total)

            def tick(item: str | None = None) -> None:
                bar.advance(task)
                bar.refresh()

            # No forced `completed=total` on exit: the bar reflects the ticks it
            # actually got, so a run that stops short reads short, not 100%.
            yield tick

    # -- indeterminate spinner ------------------------------------------------

    @contextmanager
    def spinner(self, label: str) -> Iterator[None]:
        """Indeterminate work with an elapsed timer. A live spinner at ``normal``
        on a terminal; plain ``label...`` / ``label: done (Ns)`` lines otherwise;
        silent at ``quiet``."""
        if self.verbosity is Verbosity.quiet:
            yield
            return

        if self.uses_progress_bar:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=self.console,
            ) as bar:
                bar.add_task(label, total=None)
                yield
            return

        self._print(f"{label}...")
        start = time.monotonic()
        try:
            yield
        finally:
            self._print(f"{label}: done ({time.monotonic() - start:.1f}s)")

    # -- warnings -----------------------------------------------------------

    def warn(self, message: str) -> None:
        """Record a non-fatal warning to be shown grouped by `flush_warnings`.
        Suppressed entirely at ``quiet``."""
        if self.verbosity is Verbosity.quiet:
            return
        self._warnings.append(message)

    def flush_warnings(self, heading: str = "Warnings") -> None:
        """Emit every warning recorded since the last flush as one group, then
        clear them. A no-op at ``quiet`` or with nothing pending."""
        pending, self._warnings = self._warnings, []
        if not pending or self.verbosity is Verbosity.quiet:
            return
        self._emit_block(
            title=heading,
            border_style="yellow",
            panel_body="\n".join(f"• {message}" for message in pending),
            plain_heading=f"{heading}:",
            plain_lines=[f"WARNING: {message}" for message in pending],
        )

    # -- fatal error --------------------------------------------------------

    def error(self, heading: str, message: str, *, report_path: str | Path | None = None) -> None:
        """Render a styled fatal block: `heading`, `message`, and an optional
        pointer to a report file. Emitted at every verbosity, ``quiet``
        included."""
        pointer = None if report_path is None else f"See {report_path}"
        self._emit_block(
            title=heading,
            border_style="red",
            panel_body=message if pointer is None else f"{message}\n\n{pointer}",
            plain_heading=f"ERROR: {heading}",
            plain_lines=[*(message.splitlines() or [message]), *([pointer] if pointer else [])],
        )

    def print_exception(self, exc: BaseException | None = None) -> None:
        """At ``debug`` verbosity, render a formatted traceback for `exc` (or the
        exception currently being handled). A no-op below ``debug``."""
        if self.verbosity < Verbosity.debug:
            return
        if exc is not None:
            self.console.print(
                Traceback.from_exception(type(exc), exc, exc.__traceback__)
            )
        else:
            self.console.print_exception()

    # -- retained summary line --------------------------------------------------

    def summary(self, message: str) -> None:
        """Print a retained one-line command summary to stdout, verbatim.
        Suppressed at ``quiet`` (anything parsing these lines runs without
        ``-q``)."""
        if self.verbosity is Verbosity.quiet:
            return
        self.out_console.print(message, markup=False, highlight=False)

    # -- internals --------------------------------------------------------------

    def _emit_block(
        self,
        *,
        title: str,
        border_style: str,
        panel_body: str,
        plain_heading: str,
        plain_lines: list[str],
    ) -> None:
        """A grouped diagnostic block: a `rich.Panel` on a terminal, a plain
        heading followed by prefixed lines off one. Shared by `flush_warnings`
        and `error`."""
        if self.console.is_terminal:
            self.console.print(Panel(panel_body, title=title, border_style=border_style))
        else:
            self._print(plain_heading)
            for line in plain_lines:
                self._print(line)

    def _print(self, text: str) -> None:
        """A plain line to the diagnostics console: no markup, no syntax
        highlighting, no soft-wrap surprises."""
        self.console.print(text, markup=False, highlight=False)


def _noop_tick(item: str | None = None) -> None:
    """The `Tick` handed out at ``quiet`` verbosity — advances nothing."""
