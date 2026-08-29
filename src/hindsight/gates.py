"""The two preregistered validation gates.

Both must pass before the primary outcome is computed at all. They are not
robustness checks run afterwards on a result someone already likes.

Gate 1 asks whether our copy of the archive is faithful. Gate 2 asks whether our
implementation of the rule is right. Only Gate 2 can be run at all, and only for
the US series, because someone else has already published the real-time answer.
That is the entire reason the US series are here: they are the case where the
truth is already on the table, so the method can be marked rather than trusted.
Once it reproduces a known answer it is pointed at GB settlement data, where no
equivalent archive exists and nobody can mark it.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from decimal import Decimal

from hindsight import prereg, replay
from hindsight.rules import sahm
from hindsight.sources.alfred import Alfred, RealtimeInterval


@dataclass
class GateResult:
    gate: str
    passed: bool
    n_checked: int
    n_failed: int
    max_abs_diff: Decimal | None
    failures: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        worst = "n/a" if self.max_abs_diff is None else f"{self.max_abs_diff}"
        return (
            f"[{verdict}] {self.gate}: {self.n_failed}/{self.n_checked} failed, "
            f"worst |diff| {worst}"
        )


def gate1_capture_is_faithful(
    intervals: list[RealtimeInterval],
    alfred: Alfred,
    *,
    series_id: str,
    sample_size: int = prereg.GATE1_SAMPLE_SIZE,
    seed: int = 20260901,
    tol: Decimal = prereg.RECONSTRUCTION_TOL,
) -> GateResult:
    """Our reconstruction of a vintage must equal ALFRED's own answer for it.

    Sampled triples are drawn from vintage dates we actually hold, and compared
    against a *different request shape* (`as_of`, output_type=2) than the one we
    ingested from (`realtime_intervals`, output_type=1). If both sides were
    derived the same way, agreement between them would prove nothing.

    The seed is fixed so the sample cannot be redrawn until it passes.
    """
    rng = random.Random(seed)
    vintages = sorted({iv.realtime_start for iv in intervals if iv.series_id == series_id})
    if not vintages:
        return GateResult("capture_faithful", False, 0, 0, None, [{"error": "no vintages held"}])

    picks = sorted(rng.sample(vintages, min(sample_size, len(vintages))))

    checked = failed = 0
    worst: Decimal | None = None
    failures: list[dict] = []

    for n, vintage in enumerate(picks, 1):
        if n == 1 or n % 10 == 0 or n == len(picks):
            print(f"    gate 1: {n}/{len(picks)} vintages", flush=True)
        theirs = alfred.as_of(series_id, vintage)
        ours = replay.vintage_as_of(intervals, vintage, series_id=series_id)

        for month in sorted(set(theirs) | set(ours)):
            checked += 1
            a, b = theirs.get(month), ours.get(month)
            if a is None or b is None:
                failed += 1
                failures.append(
                    {"vintage": str(vintage), "month": str(month),
                     "theirs": a, "ours": b, "reason": "present on one side only"}
                )
                continue
            diff = abs(Decimal(str(a)) - Decimal(str(b)))
            worst = diff if worst is None else max(worst, diff)
            if diff > tol:
                failed += 1
                failures.append(
                    {"vintage": str(vintage), "month": str(month),
                     "theirs": str(a), "ours": str(b), "diff": str(diff)}
                )

    return GateResult(
        "capture_faithful", failed == 0, checked, failed, worst, failures[:50]
    )


def gate2_rule_reproduces_benchmark(
    intervals: list[RealtimeInterval],
    alfred: Alfred,
    *,
    series_id: str = "UNRATE",
    benchmark: str = prereg.GATE2_BENCHMARK_SERIES,
    freeze: dt.date | None = None,
    tol: Decimal = prereg.RECONSTRUCTION_TOL,
) -> GateResult:
    """Our real-time Sahm gap must equal FRED's published real-time Sahm series.

    This is the gate that matters. If it fails, the failure is published and the
    GB extension does not run -- because there would be no evidence the method
    works anywhere it *can* be checked, and the GB data cannot check it.
    """
    freeze = freeze or prereg.FREEZE_DATE
    # The benchmark has its own vintage calendar. Ask for the latest vintage at
    # or before the freeze date, never for the freeze date itself.
    candidates = [v for v in alfred.vintage_dates(benchmark) if v <= freeze]
    if not candidates:
        return GateResult(
            "rule_reproduces", False, 0, 0, None,
            [{"error": f"{benchmark} has no vintage at or before {freeze}"}],
        )
    theirs = alfred.as_of(benchmark, candidates[-1])
    first_pub = replay.first_publication_dates(intervals, series_id=series_id)

    checked = failed = 0
    worst: Decimal | None = None
    failures: list[dict] = []

    for month in sorted(first_pub):
        if not (prereg.WINDOW_START <= month <= prereg.WINDOW_END):
            continue
        if month not in theirs:
            continue

        vintage = replay.vintage_as_of(intervals, first_pub[month], series_id=series_id)
        point = {p.month: p for p in sahm.compute(vintage)}.get(month)
        if point is None or point.gap is None:
            continue

        checked += 1
        diff = abs(point.gap - Decimal(str(theirs[month])))
        worst = diff if worst is None else max(worst, diff)
        if diff > tol:
            failed += 1
            failures.append(
                {"month": str(month), "ours": str(point.gap),
                 "theirs": str(theirs[month]), "diff": str(diff)}
            )

    coverage = replay.coverage(intervals, series_id=series_id)
    passed = failed == 0 and checked > 0 and coverage >= prereg.MIN_VINTAGE_COVERAGE
    if coverage < prereg.MIN_VINTAGE_COVERAGE:
        failures.append(
            {"reason": "coverage below preregistered floor",
             "coverage": f"{coverage:.4f}", "floor": str(prereg.MIN_VINTAGE_COVERAGE)}
        )

    return GateResult("rule_reproduces", passed, checked, failed, worst, failures[:50])


def gate2b_under_benchmark_convention(
    intervals: list[RealtimeInterval],
    alfred: Alfred,
    *,
    series_id: str = "UNRATE",
    benchmark: str = prereg.GATE2_BENCHMARK_SERIES,
    release_offset: int = prereg.GATE2B_RELEASE_OFFSET,
    freeze: dt.date | None = None,
    tol: Decimal = prereg.RECONSTRUCTION_TOL,
) -> GateResult:
    """Gate 2 again, under the benchmark's own vintage convention.

    **This gate was designed after seeing Gate 2 fail.** It is therefore weaker
    evidence than Gate 2 would have been, and it never replaces it: Gate 2's
    failure stays on the record in METHODS.md and in gates.json. See
    PREREGISTRATION.md, Amendment 2.

    Gate 2 asks whether our gap matches the benchmark using the vintage current
    on the day a month was released. Three Decembers said no, and each was
    reproduced exactly by the vintage one release later -- the release carrying
    the annual seasonal adjustment revision.

    This gate applies that offset uniformly rather than carving out December,
    because a rule that says 'use the next vintage, but only for the months where
    that helps' is not a convention, it is a fit.
    """
    freeze = freeze or prereg.FREEZE_DATE
    candidates = [v for v in alfred.vintage_dates(benchmark) if v <= freeze]
    if not candidates:
        return GateResult(
            "rule_reproduces_offset", False, 0, 0, None,
            [{"error": f"{benchmark} has no vintage at or before {freeze}"}],
        )
    theirs = alfred.as_of(benchmark, candidates[-1])

    vintages = sorted({iv.realtime_start for iv in intervals if iv.series_id == series_id})
    first_pub = replay.first_publication_dates(intervals, series_id=series_id)

    checked = failed = 0
    worst: Decimal | None = None
    failures: list[dict] = []

    for month in sorted(first_pub):
        if not (prereg.WINDOW_START <= month <= prereg.WINDOW_END):
            continue
        if month not in theirs:
            continue

        later = [v for v in vintages if v > first_pub[month]]
        if len(later) < release_offset:
            continue  # not enough releases have happened since
        as_of = first_pub[month] if release_offset == 0 else later[release_offset - 1]

        vintage = replay.vintage_as_of(intervals, as_of, series_id=series_id)
        point = {p.month: p for p in sahm.compute(vintage)}.get(month)
        if point is None or point.gap is None:
            continue

        checked += 1
        diff = abs(point.gap - Decimal(str(theirs[month])))
        worst = diff if worst is None else max(worst, diff)
        if diff > tol:
            failed += 1
            failures.append(
                {"month": str(month), "vintage_used": str(as_of),
                 "ours": str(point.gap), "theirs": str(theirs[month]),
                 "diff": str(diff)}
            )

    return GateResult(
        "rule_reproduces_offset", failed == 0 and checked > 0,
        checked, failed, worst, failures[:50]
    )
