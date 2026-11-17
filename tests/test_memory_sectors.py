"""The sectors' clustering in a search's memory estimate (search.memory_needed's term WARD_SPOT_BYTES x
min(lines, mapping.SECTOR_WARD_SPOTS)²) and the one inversion of the estimate (search.lines_fitting): the refusals'
and the worker's warning "fits"."""

import inspect
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import mapping  # noqa: E402
import search  # noqa: E402
from settings import PUBLIC, Limits  # noqa: E402

GIB = 2 ** 30


def test_memory_needed_counts_the_sectors(monkeypatch):
    """The term follows the lines up to SECTOR_WARD_SPOTS (a run has at most as many spots as lines), then stays;
    without lines memory_needed is the grids' alone, byte for byte (the quick lane's reserve, the tiles' side)."""
    cap = mapping.SECTOR_WARD_SPOTS
    assert search.WARD_SPOT_BYTES == 8 and cap == 10_000
    assert search.memory_needed(1, 0) == search.PIXEL_BYTES
    assert search.memory_needed(search.MAX_MEASURED_PX ** 2, 0) == search.MAX_MEASURED_PX ** 2 * search.PIXEL_BYTES
    assert search.memory_needed(36e6, 0) == 36e6 * search.PIXEL_BYTES
    plain = lambda pixels, lines, points=0: (pixels * search.PIXEL_BYTES + lines * search.LINE_BYTES  # noqa: E731
                                             + points * search.PROFILE_POINT_BYTES)
    for lines in (1, 2, 4_000, cap - 1, cap, cap + 1, 1_500_000):
        for pixels, points in ((0, 0), (1000, 0), (64e6, 0), (0, 37 * lines)):
            term = 8 * min(lines, cap) ** 2
            assert search.memory_needed(pixels, lines, points) == plain(pixels, lines, points) + term, (lines, pixels)
    assert search.memory_needed(0, 1_500_000) - search.memory_needed(0, 1_500_000 - 1) == search.LINE_BYTES
    assert search.memory_needed(0, cap) - plain(0, cap) == 800_000_000  # the 800 MB measured at 10 000 spots
    monkeypatch.setattr(mapping, "SECTOR_WARD_SPOTS", 12)  # read at call time: the term follows the cap
    assert search.memory_needed(0, 100) == 100 * search.LINE_BYTES + 8 * 144


def _assert_inverts(budget, pixels, per_line):
    fits = search.lines_fitting(budget, pixels, per_line)
    need = lambda n: search.memory_needed(pixels, n, n * per_line)  # noqa: E731
    assert isinstance(fits, int) and fits >= 0
    if fits:
        assert need(fits) <= budget, (budget, pixels, per_line, fits)
    assert need(fits + 1) > budget, (budget, pixels, per_line, fits)
    return fits


@pytest.mark.parametrize("line_bytes", [450, 900, 1_234])
def test_lines_fitting_inverts_memory_needed(monkeypatch, line_bytes):
    """memory_needed(pixels, fits) <= budget < memory_needed(pixels, fits + 1) (0 when no line fits), over budgets,
    pixels and bytes a line (LINE_BYTES and a circle's profile points a line), below, at and above the cap."""
    monkeypatch.setattr(search, "LINE_BYTES", line_bytes)
    cap = mapping.SECTOR_WARD_SPOTS
    for pixels in (0, 1, 300 * 300, 36e6, 64e6):
        grids = search.memory_needed(pixels, 0)
        for per_line in (0, 0.5, 9, 37.25, 203):
            need = lambda n: search.memory_needed(pixels, n, n * per_line)  # noqa: E731
            budgets = {grids - 1, grids, grids + 1, need(1) - 1, need(1), need(1) + 1, grids + 1e6, grids + 1e8,
                       grids + 5e9, grids + 3.7e10}
            for n in (cap // 2, cap - 1, cap, cap + 1, 2 * cap, 1_450_644, 2_339_533):
                budgets |= {need(n) - 1, need(n) - 0.5, need(n), need(n) + 0.5, need(n + 1) - 1}
            for budget in sorted(budgets):
                if budget < 0:
                    continue
                for value in (budget, int(budget)):
                    _assert_inverts(value, pixels, per_line)
            for n in (1, 7, cap - 1, cap, cap + 1, 3 * cap + 17):
                assert search.lines_fitting(need(n), pixels, per_line) == n  # a round trip: the tests' memory
                assert search.lines_fitting(int(need(n)), pixels, per_line) in (n - 1, n)
    assert search.lines_fitting(-5, 0) == 0 and search.lines_fitting(0, 0) == 0
    assert search.lines_fitting(search.memory_needed(1000, 0), 1000) == 0  # the grids fill it: no line


def test_lines_fitting_by_brute_force(monkeypatch):
    """With a small cap every count is checked against a walk over memory_needed: below, at and above the cap."""
    monkeypatch.setattr(mapping, "SECTOR_WARD_SPOTS", 12)
    for pixels in (0, 3):
        for per_line in (0, 0.5, 9):
            need = lambda n: search.memory_needed(pixels, n, n * per_line)  # noqa: E731
            for budget in range(0, int(need(40)), 97):
                walked = 0
                while need(walked + 1) <= budget:
                    walked += 1
                assert search.lines_fitting(budget, pixels, per_line) == walked, (budget, pixels, per_line)


def test_the_callers_invert_by_the_helper():
    """The refusals and the warning name their "fits" by lines_fitting only: no inversion by hand is left."""
    source = inspect.getsource(search)
    assert "// LINE_BYTES" not in source and "memory_needed(0, 1" not in source
    for function in (search.memory_warning, search._check_lines, search._early_check, search._estimate_check):
        assert "lines_fitting(" in inspect.getsource(function), function.__name__


def test_acceptance_numbers(monkeypatch):
    """Numbers computed by hand with the formulas before the term: a worker with 18 GiB free, 3 compute slots and 2
    download slots has a slot of about 4.94 GiB; the largest public search (64 Mpx, 1 500 000 lines) needs 4.24 GiB
    without the term and about 4.98 GiB with it; the lines that fit a slot go from 2 339 533 to 1 450 644, which
    memory_warning names; with 19 GiB free it does not warn."""
    slots = Limits(**PUBLIC).model_copy(update={"compute_slots": 3, "download_slots": 2})
    monkeypatch.setattr(search, "available_memory", lambda: 18 * GIB)
    slot = search.slot_memory(slots)
    assert slot == 5_305_580_032 and round(slot / GIB, 2) == 4.94
    pixels, lines = slots.grid_mpx_max * 1e6, slots.lines_max
    assert (pixels, lines) == (64e6, 1_500_000)
    today = pixels * search.PIXEL_BYTES + lines * search.LINE_BYTES  # main's formula, without the term
    assert round(today / GIB, 2) == 4.24
    assert round(search.memory_needed(pixels, lines) / GIB, 2) == 4.98
    assert int((slot - pixels * search.PIXEL_BYTES) // search.LINE_BYTES) == 2_339_533  # main's inversion
    assert search.lines_fitting(slot, pixels) == 1_450_644
    warning = search.memory_warning(slots, slot)
    assert warning and "FINDALINE_LIMIT_LINES_MAX=1450644" in warning, warning
    assert "needs about 5.0 GiB, 4.9 GiB for each of 3 compute slots" in warning, warning
    monkeypatch.setattr(search, "available_memory", lambda: 19 * GIB)
    assert search.memory_warning(slots, search.slot_memory(slots)) is None
