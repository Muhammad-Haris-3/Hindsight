"""The gates gate. Enforced, not merely described.

PREREGISTRATION.md says both gates must pass *before the primary outcome is
computed at all*, and names this file as what enforces it. Prose cannot enforce
anything, so the promise is split into two kinds of check:

  * **Behaviour** -- the gates fail when they should. A gate that cannot fail is
    decoration, and the way a gate stops being able to fail is rarely dramatic:
    a tolerance quietly widened, a coverage floor that stops being consulted, a
    comparison that skips the months it cannot make.

  * **The record on disk** -- `artifacts/` may not contain a finding the gates
    did not permit. That check runs against the real repository rather than a
    fixture, so it fails if anybody ever computes the outcome past a red gate.

The gates are marked here against synthetic archives whose right answers are
known by construction. Gate 1 and Gate 2 are themselves the marking of the
*method* against ALFRED; this file marks the marking.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from hindsight import gates, prereg, replay
from hindsight.rules import sahm
from hindsight.sources.alfred import RealtimeInterval

ROOT = Path(__file__).resolve().parents[1]
FOREVER = dt.date(9999, 12, 31)


# --- an archive whose answers are known by construction ----------------------


def month(y: int, m: int) -> dt.date:
    return dt.date(y, m, 1)


def _next_month(m: dt.date) -> dt.date:
    return month(m.year + 1, 1) if m.month == 12 else month(m.year, m.month + 1)


def _release_day(m: dt.date) -> dt.date:
    """This archive publishes month m early in the following month."""
    nxt = _next_month(m)
    return dt.date(nxt.year, nxt.month, 5)


# Building the 528-month fixture and its benchmark costs a Sahm evaluation per
# month; six tests want the same one. Memoised so the offline suite stays the
# few seconds it has to be to run on every push.
_ARCHIVES: dict[tuple[dt.date, dt.date], list[RealtimeInterval]] = {}
_BENCHMARKS: dict[int, dict[dt.date, float]] = {}


def full_archive(
    *, start: dt.date = month(1974, 1), end: dt.date = prereg.WINDOW_END
) -> list[RealtimeInterval]:
    """One never-revised interval per month, spanning the preregistered window.

    Coverage has to be real: gate 2 consults `prereg.MIN_VINTAGE_COVERAGE`
    against the whole 528-month window, so a fixture holding a handful of months
    would fail the gate for the wrong reason and prove nothing about the rest of
    it. The series wanders, in tenths of a point, so the twelve-month minimum is
    not degenerate.
    """
    if (start, end) in _ARCHIVES:
        return list(_ARCHIVES[(start, end)])

    out: list[RealtimeInterval] = []
    m, i = start, 0
    while m <= end:
        phase = i % 36
        rate = 5.0 + (phase if phase < 18 else 36 - phase) / 10
        out.append(
            RealtimeInterval("UNRATE", m, round(rate, 1), _release_day(m), FOREVER)
        )
        m = _next_month(m)
        i += 1

    _ARCHIVES[(start, end)] = out
    return list(out)


def benchmark_from(intervals: list[RealtimeInterval]) -> dict[dt.date, float]:
    """What a perfect benchmark would publish for this archive.

    Built by the same route gate 2 walks -- the vintage current on each month's
    release day -- so a gate run against it must pass. Every failing case below
    is this mapping with one number moved, which makes the size of the move the
    only thing under test. Callers get a copy: one of them moves a number.
    """
    key = hash(tuple(intervals))
    if key in _BENCHMARKS:
        return dict(_BENCHMARKS[key])

    first_pub = replay.first_publication_dates(intervals, series_id="UNRATE")
    out: dict[dt.date, float] = {}
    for m, pub in first_pub.items():
        vintage = replay.vintage_as_of(intervals, pub, series_id="UNRATE")
        point = {p.month: p for p in sahm.compute(vintage)}.get(m)
        if point is not None and point.gap is not None:
            out[m] = float(point.gap)

    _BENCHMARKS[key] = out
    return dict(out)


class FakeAlfred:
    """Stands in for the API. Answers only what the gates ask it."""

    def __init__(
        self,
        *,
        as_of: dict[tuple[str, dt.date], dict[dt.date, float]] | None = None,
        benchmark: dict[dt.date, float] | None = None,
        benchmark_vintages: list[dt.date] | None = None,
    ) -> None:
        self.by_vintage = as_of or {}
        self.benchmark = benchmark or {}
        self.benchmark_vintages = benchmark_vintages or [dt.date(2026, 8, 7)]

    def vintage_dates(self, series_id: str) -> list[dt.date]:
        return list(self.benchmark_vintages)

    def as_of(self, series_id: str, vintage: dt.date) -> dict[dt.date, float]:
        if series_id == prereg.GATE2_BENCHMARK_SERIES:
            return dict(self.benchmark)
        return dict(self.by_vintage[(series_id, vintage)])


def mirror(intervals: list[RealtimeInterval]) -> FakeAlfred:
    """A FakeAlfred agreeing with our own reconstruction everywhere."""
    vintages = sorted({iv.realtime_start for iv in intervals})
    return FakeAlfred(
        as_of={
            ("UNRATE", v): replay.vintage_as_of(intervals, v, series_id="UNRATE")
            for v in vintages
        }
    )


@pytest.fixture(scope="module")
def outcome_module():
    """`scripts/outcome.py` is a script, so it is loaded by path, not imported."""
    spec = importlib.util.spec_from_file_location(
        "hindsight_outcome_script", ROOT / "scripts" / "outcome.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- gate 1: the capture is faithful -----------------------------------------


def test_gate1_passes_when_the_reconstruction_agrees():
    intervals = full_archive(start=month(2010, 1), end=month(2012, 12))
    result = gates.gate1_capture_is_faithful(
        intervals, mirror(intervals), series_id="UNRATE"
    )
    assert result.passed
    assert result.n_failed == 0
    assert result.n_checked > 0, "a gate that checked nothing has not passed"


def test_gate1_fails_when_one_value_disagrees():
    intervals = full_archive(start=month(2010, 1), end=month(2012, 12))
    alfred = mirror(intervals)
    victim = sorted(alfred.by_vintage)[5]
    target = sorted(alfred.by_vintage[victim])[0]
    alfred.by_vintage[victim][target] += 0.1

    result = gates.gate1_capture_is_faithful(intervals, alfred, series_id="UNRATE")
    assert not result.passed
    assert result.n_failed == 1


def test_gate1_fails_when_a_month_is_present_on_one_side_only():
    """A missing month fails loudly, never as a period nobody published."""
    intervals = full_archive(start=month(2010, 1), end=month(2012, 12))
    alfred = mirror(intervals)
    victim = sorted(alfred.by_vintage)[5]
    alfred.by_vintage[victim].pop(sorted(alfred.by_vintage[victim])[0])

    result = gates.gate1_capture_is_faithful(intervals, alfred, series_id="UNRATE")
    assert not result.passed
    assert any(f.get("reason") == "present on one side only" for f in result.failures)


@pytest.mark.parametrize(
    "delta,should_pass",
    [(0.004, True), (0.005, True), (0.006, False), (0.01, False)],
)
def test_gate1_honours_the_preregistered_tolerance_exactly(delta, should_pass):
    """The tolerance is 0.005, neither widened nor tightened in passing.

    Widening it is the obvious repair after a failure, which is why the number
    is preregistered and why the boundary is asserted rather than assumed.
    """
    assert prereg.RECONSTRUCTION_TOL == Decimal("0.005")
    intervals = full_archive(start=month(2010, 1), end=month(2011, 12))
    alfred = mirror(intervals)
    victim = sorted(alfred.by_vintage)[3]
    target = sorted(alfred.by_vintage[victim])[0]
    alfred.by_vintage[victim][target] = round(
        alfred.by_vintage[victim][target] + delta, 6
    )

    result = gates.gate1_capture_is_faithful(intervals, alfred, series_id="UNRATE")
    assert result.passed is should_pass


def test_gate1_fails_rather_than_passes_when_nothing_was_captured():
    result = gates.gate1_capture_is_faithful([], FakeAlfred(), series_id="UNRATE")
    assert not result.passed, "an empty archive must not pass by vacuity"


def test_gate1_sample_cannot_be_redrawn_until_it_passes():
    """The seed is fixed, so the same archive yields the same sample every run."""
    intervals = full_archive(start=month(2010, 1), end=month(2014, 12))
    a = gates.gate1_capture_is_faithful(intervals, mirror(intervals), series_id="UNRATE")
    b = gates.gate1_capture_is_faithful(intervals, mirror(intervals), series_id="UNRATE")
    assert a.n_checked == b.n_checked


# --- gate 2: the rule reproduces the benchmark -------------------------------


def test_gate2_passes_against_a_benchmark_that_agrees():
    intervals = full_archive()
    result = gates.gate2_rule_reproduces_benchmark(
        intervals, FakeAlfred(benchmark=benchmark_from(intervals))
    )
    assert result.passed, result.failures[:3]
    assert result.n_checked > 500, "the window is 528 months; a partial check is no pass"


def test_gate2_fails_when_one_month_disagrees():
    intervals = full_archive()
    bench = benchmark_from(intervals)
    bench[month(1981, 12)] = round(bench[month(1981, 12)] + 0.2, 6)

    result = gates.gate2_rule_reproduces_benchmark(
        intervals, FakeAlfred(benchmark=bench)
    )
    assert not result.passed
    assert result.n_failed == 1
    assert result.failures[0]["month"] == "1981-12-01"


def test_gate2_fails_when_coverage_is_below_the_preregistered_floor():
    """Agreement on the months we hold is not a pass if we hold too few.

    A gap in collection reading as a period in which nothing disagreed is the
    exact failure the coverage floor exists to prevent, and it is the one that
    looks most like success from the outside.
    """
    intervals = [
        iv for iv in full_archive() if not (1990 <= iv.ref_period_start.year <= 2005)
    ]
    result = gates.gate2_rule_reproduces_benchmark(
        intervals, FakeAlfred(benchmark=benchmark_from(full_archive()))
    )

    assert replay.coverage(intervals, series_id="UNRATE") < prereg.MIN_VINTAGE_COVERAGE
    assert not result.passed
    assert any("coverage" in f.get("reason", "") for f in result.failures)


def test_gate2_fails_when_the_benchmark_has_no_vintage_at_the_freeze_date():
    intervals = full_archive()
    alfred = FakeAlfred(
        benchmark=benchmark_from(intervals),
        benchmark_vintages=[dt.date(2027, 1, 1)],  # every vintage after the freeze
    )
    assert not gates.gate2_rule_reproduces_benchmark(intervals, alfred).passed


def test_gate2_never_reads_past_the_release_day():
    """The gate uses the vintage current on release day, never a later one.

    If a revision that arrived afterwards can reach the rule, the gate marks a
    method the project does not use -- and the difference is invisible in the
    verdict, because both versions pass on an archive nobody revised.
    """
    intervals = full_archive()
    target = month(1995, 6)
    pub = replay.first_publication_dates(intervals, series_id="UNRATE")[target]

    # Restate an *earlier* month one day after `target` was published. It feeds
    # the twelve-month minimum, so a gate reading a later vintage would see it.
    earlier = month(1995, 1)
    revised: list[RealtimeInterval] = []
    for iv in intervals:
        if iv.ref_period_start != earlier:
            revised.append(iv)
            continue
        revised.append(
            RealtimeInterval(iv.series_id, iv.ref_period_start, iv.value,
                             iv.realtime_start, pub)
        )
        revised.append(
            RealtimeInterval(iv.series_id, iv.ref_period_start, round(iv.value - 1.0, 1),
                             pub + dt.timedelta(days=1), FOREVER)
        )

    # The benchmark still holds release-day values, which the revision cannot
    # touch. A gate leaking the later vintage would now disagree for 1995-06.
    result = gates.gate2_rule_reproduces_benchmark(
        revised, FakeAlfred(benchmark=benchmark_from(intervals))
    )
    assert not any(f.get("month") == str(target) for f in result.failures)


# --- gate 2b is post-hoc, and never stands in for gate 2 ---------------------


def test_gate2b_is_marked_post_hoc_in_the_preregistration():
    assert prereg.GATE2B_IS_POST_HOC is True
    assert prereg.GATE2B_RELEASE_OFFSET == 1


def test_gate2b_applies_its_offset_to_every_month():
    """On an archive nobody revised, both conventions see the same numbers.

    The offset is a choice of vintage, not a choice of months: a version that
    carved out the months where it helps would pass by construction.
    """
    intervals = full_archive()
    alfred = FakeAlfred(benchmark=benchmark_from(intervals))
    assert gates.gate2_rule_reproduces_benchmark(intervals, alfred).passed
    assert gates.gate2b_under_benchmark_convention(intervals, alfred).passed


def test_gate2b_passing_cannot_license_a_finding(outcome_module, tmp_path):
    """Gate 2b is recorded, not decisive. Gate 2's verdict is the binding one."""
    outcome_module.GATES = _write_gates(
        tmp_path / "g.json",
        [
            {"gate": "capture_faithful", "passed": True, "n_checked": 10, "n_failed": 0},
            {"gate": "rule_reproduces", "passed": False, "n_checked": 528, "n_failed": 3},
            {"gate": "rule_reproduces_offset", "passed": True, "n_checked": 528,
             "n_failed": 0, "post_hoc": True},
        ],
    )
    reason = outcome_module.check_gates()
    assert reason is not None
    assert "rule_reproduces" in reason


# --- the refusal path: no finding without a green gate -----------------------


PASSING = [
    {"gate": "capture_faithful", "passed": True, "n_checked": 10, "n_failed": 0},
    {"gate": "rule_reproduces", "passed": True, "n_checked": 528, "n_failed": 0},
]


def _write_gates(path: Path, results: list[dict], freeze: str | None = None) -> Path:
    path.write_text(
        json.dumps(
            {"freeze_date": freeze or prereg.FREEZE_DATE.isoformat(), "results": results}
        ),
        encoding="utf-8",
    )
    return path


def test_outcome_refuses_when_no_gates_were_run(outcome_module, tmp_path):
    outcome_module.GATES = tmp_path / "absent.json"
    assert outcome_module.check_gates() is not None


def test_outcome_refuses_when_a_gate_is_missing_from_the_record(outcome_module, tmp_path):
    outcome_module.GATES = _write_gates(tmp_path / "g.json", PASSING[:1])
    reason = outcome_module.check_gates()
    assert reason is not None and "never run" in reason


def test_outcome_refuses_when_the_freeze_date_does_not_match(outcome_module, tmp_path):
    """Gates run at some other freeze date are gates for some other study."""
    outcome_module.GATES = _write_gates(tmp_path / "g.json", PASSING, freeze="2025-01-01")
    reason = outcome_module.check_gates()
    assert reason is not None and "freeze date" in reason


def test_outcome_permits_a_finding_only_when_both_gates_passed(outcome_module, tmp_path):
    outcome_module.GATES = _write_gates(tmp_path / "g.json", PASSING)
    assert outcome_module.check_gates() is None


# --- the same rule, applied to the real repository ---------------------------


def test_a_recorded_gate_run_says_where_it_read_from():
    """Gate 1 tests "our storage and our joins" only if it read from the store.

    Reading from the API instead is a valid run of the gate's arithmetic and an
    invalid run of its premise, and the verdict looks identical either way. So
    the source is recorded and checked, rather than inferred from whichever
    branch of `run_gates.py` someone believes ran.
    """
    path = ROOT / "artifacts" / "gates.json"
    if not path.exists():
        pytest.skip("no gate run recorded")

    source = json.loads(path.read_text(encoding="utf-8")).get("intervals_from")
    assert source in ("store", "alfred-api"), (
        f"artifacts/gates.json records intervals_from={source!r}. A gate run that "
        "does not say where it read from cannot support Gate 1's premise."
    )


def test_the_recorded_gates_agree_with_the_published_status(outcome_module):
    """`artifacts/` may not hold a finding the gates on disk did not permit.

    The only test here that reads the real artifacts, and the one that would
    catch the failure that actually matters: an outcome computed anyway.
    """
    artifacts = ROOT / "artifacts"
    outcome_module.GATES = artifacts / "gates.json"
    permitted = outcome_module.check_gates() is None

    assert permitted or not (artifacts / "outcome.json").exists(), (
        "artifacts/outcome.json exists although the recorded gates do not permit "
        "a finding. PREREGISTRATION.md says the outcome is not computed."
    )
