"""`sndocs.parallel.parallel_map`: the shared "run over a process pool, tick a
callback as each finishes" helper `normalize` uses and (issue #49) `build`'s
minify pass will reuse. Assertions are on the contract — results in input order,
`on_result` once per item — not on scheduling."""

from __future__ import annotations

import os

import pytest

from sndocs.parallel import parallel_map

# Module-level so the process pool can pickle them.


def _double(value: int) -> int:
    return value * 2


def _pid_of(value: int) -> tuple[int, int]:
    return value, os.getpid()


_SEED: str = ""


def _seed_worker(value: str) -> None:
    global _SEED
    _SEED = value


def _read_seed(_ignored: int) -> str:
    return _SEED


def test_serial_path_preserves_order_and_ticks_once_per_item() -> None:
    seen: list[int] = []

    results = parallel_map(_double, [1, 2, 3, 4], workers=1, on_result=seen.append)

    assert results == [2, 4, 6, 8]
    assert sorted(seen) == [2, 4, 6, 8]
    assert len(seen) == 4


def test_empty_and_single_item_run_inline() -> None:
    assert parallel_map(_double, [], workers=4) == []

    seen: list[int] = []
    assert parallel_map(_double, [21], workers=4, on_result=seen.append) == [42]
    assert seen == [42]


def test_parallel_path_returns_results_in_input_order() -> None:
    items = list(range(50))
    seen: list[int] = []

    results = parallel_map(_double, items, workers=4, on_result=seen.append)

    assert results == [v * 2 for v in items]  # input order, not completion order
    assert sorted(seen) == sorted(v * 2 for v in items)
    assert len(seen) == len(items)


def test_parallel_path_actually_uses_worker_processes() -> None:
    results = parallel_map(_pid_of, list(range(20)), workers=4)

    worker_pids = {pid for _, pid in results}
    assert worker_pids and os.getpid() not in worker_pids


def test_initializer_seeds_each_worker() -> None:
    results = parallel_map(
        _read_seed, list(range(8)), workers=2, initializer=_seed_worker, initargs=("hello",)
    )
    assert results == ["hello"] * 8


def test_zero_workers_is_rejected() -> None:
    with pytest.raises(ValueError):
        parallel_map(_double, [1], workers=0)
