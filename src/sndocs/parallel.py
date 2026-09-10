"""Run a function over many items in a process pool, ticking a callback as each
one finishes.

`sndocs normalize` and (issue #49) `sndocs build`'s minify pass both walk a few
thousand files through a `ProcessPoolExecutor` and both want a progress bar that
advances on *actual* per-item completion rather than in fixed-size chunks. This
module is that shared shape: `parallel_map` submits every item, calls `on_result`
once per finished item in completion order (so a live bar reads honestly), and
returns the results in the original item order. A serial path — one worker, or a
single item — runs inline and calls `on_result` identically, so the caller's
progress wiring is the same either way.

The `executor.submit` + `concurrent.futures.as_completed` loop here replaces the
older `executor.map(..., chunksize=16)` calls, which only surfaced a whole chunk
at a time.
"""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def parallel_map(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    workers: int,
    on_result: Callable[[R], None] | None = None,
    initializer: Callable[..., object] | None = None,
    initargs: tuple[object, ...] = (),
    mp_context: str = "fork",
) -> list[R]:
    """Apply `func` to every item, returning the results in the original order.

    `on_result`, if given, is invoked once with each result as it becomes
    available — in completion order for the parallel path, in item order for the
    serial one. Use it to advance a progress bar or log a finished item.

    With `workers == 1`, or one item or fewer, everything runs inline in this
    process and `initializer` / `initargs` are ignored (there is no pool to seed).
    Otherwise a `ProcessPoolExecutor` with `max_workers=workers` runs the work,
    seeded per worker with `initializer(*initargs)`; `func`, the items, and the
    results must all be picklable. `mp_context` names the multiprocessing start
    method for the pool (default ``fork``, matching the rest of the package).
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")
    materialized = list(items)
    report = on_result if on_result is not None else _ignore

    if workers == 1 or len(materialized) <= 1:
        results: list[R] = []
        for item in materialized:
            result = func(item)
            results.append(result)
            report(result)
        return results

    ordered: list[R] = [None] * len(materialized)  # type: ignore[list-item]
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context(mp_context),
        initializer=initializer,
        initargs=initargs,
    ) as executor:
        index_of = {
            executor.submit(func, item): position
            for position, item in enumerate(materialized)
        }
        for future in as_completed(index_of):
            result = future.result()
            ordered[index_of[future]] = result
            report(result)
    return ordered


def _ignore(_result: object) -> None:
    """The `on_result` used when the caller passes none."""
