"""Replay tests, built on a synthetic archive whose answer was worked out by hand.

The fixture's point is that the revision it contains is small and entirely
plausible -- 0.15pp, on a month that is not the month being decided -- and it
still erases five firings. Nothing here touches the network.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from hindsight import prereg, replay
from hindsight.rules import sahm
from hindsight.sources.alfred import RealtimeInterval

FOREVER = dt.date(9999, 12, 31)
TROUGH = dt.date(1992, 3, 1)
RESTATED_ON = dt.date(1995, 6, 1)


def month(y: int, m: int) -> dt.date:
    return dt.date(y, m, 1)


def build_archive(*, revise_trough_to: str | None) -> list[RealtimeInterval]:
    """Three years of unemployment: a dip in early 1992, then recovery.

    The dip is the unique minimum of the three-month average, so it is the value
    the rule subtracts for the following twelve months. Revising it upward lifts
    the floor and closes the gap -- without touching a single month the rule
    averages. That is the whole mechanism, in one fixture.
    """
    months = [month(1990 + i // 12, i % 12 + 1) for i in range(36)]
    values = {m: "4.4" for m in months}
    for m in (month(1992, 1), month(1992, 2), month(1992, 3)):
        values[m] = "3.9"
    for m, v in zip(
        (month(1992, 10), month(1992, 11), month(1992, 12)), ("4.35", "4.40", "4.45")
    ):
        values[m] = v

    ivs: list[RealtimeInterval] = []
    for m in months:
        carry, nxt = divmod(m.month, 12)
        pub = month(m.year + carry, nxt + 1)  # published the month after
        ivs.append(
            RealtimeInterval("UNRATE", m, Decimal(values[m]), pub, FOREVER)
        )

    if revise_trough_to is not None:
        original = next(i for i in ivs if i.ref_period_start == TROUGH)
        ivs.remove(original)
        # The original interval closes; a new row opens. Nothing is overwritten.
        ivs.append(
            RealtimeInterval(
                "UNRATE",
                TROUGH,
                original.value,
                original.realtime_start,
                RESTATED_ON - dt.timedelta(days=1),
            )
        )
        ivs.append(
            RealtimeInterval(
                "UNRATE", TROUGH, Decimal(revise_trough_to), RESTATED_ON, FOREVER
            )
        )

    return ivs


# --- the archive behaves like an archive ------------------------------------


def test_vintage_as_of_sees_only_what_was_current():
    ivs = build_archive(revise_trough_to="4.05")

    before = replay.vintage_as_of(
        ivs, RESTATED_ON - dt.timedelta(days=1), series_id="UNRATE"
    )
    after = replay.vintage_as_of(ivs, RESTATED_ON, series_id="UNRATE")

    assert before[TROUGH] == Decimal("3.9")
    assert after[TROUGH] == Decimal("4.05")


def test_vintage_as_of_excludes_unpublished_months():
    """A period is invisible before the day it was first published."""
    ivs = build_archive(revise_trough_to=None)
    early = replay.vintage_as_of(ivs, dt.date(1990, 6, 15), series_id="UNRATE")
    assert month(1990, 5) in early
    assert month(1990, 6) not in early


# --- the primary outcome -----------------------------------------------------


def test_no_flip_when_nothing_is_revised():
    ivs = build_archive(revise_trough_to=None)
    assert replay.flips(ivs, freeze=dt.date(1996, 1, 1)) == []


def test_a_small_revision_erases_five_firings():
    """Worked by hand: real-time gap 0.50 at five months, 0.45 after restatement.

    The revised month is 1992-03. Four of the five erased months (June-September)
    and the fifth (December) are months whose own values never changed.
    """
    ivs = build_archive(revise_trough_to="4.05")
    result = replay.flips(ivs, freeze=dt.date(1996, 1, 1))

    assert [f.month for f in result] == [
        month(1992, 6),
        month(1992, 7),
        month(1992, 8),
        month(1992, 9),
        month(1992, 12),
    ]
    for f in result:
        assert f.fired_in_real_time is True
        assert f.fires_now is False
        assert f.direction == "vanished"
        assert f.gap_then == Decimal("0.50")
        assert f.gap_now == Decimal("0.45")
        assert f.month != TROUGH, "the erased months are not the revised month"


def test_flip_never_computed_from_truncated_modern_series():
    """Guard against the failure mode named in replay.flips' docstring.

    Truncating today's series at month m is not the same as the vintage that
    existed at m. If it were, these two answers would agree.
    """
    ivs = build_archive(revise_trough_to="4.05")
    firing = month(1992, 9)

    today = replay.vintage_as_of(ivs, dt.date(1996, 1, 1), series_id="UNRATE")
    truncated = {m: v for m, v in today.items() if m <= firing}
    naive = {p.month: p for p in sahm.compute(truncated)}[firing]

    pub = replay.first_publication_dates(ivs, series_id="UNRATE")[firing]
    then = replay.vintage_as_of(ivs, pub, series_id="UNRATE")
    honest = {p.month: p for p in sahm.compute(then)}[firing]

    assert naive.fires is False
    assert honest.fires is True


# --- the arithmetic ----------------------------------------------------------


def test_gap_of_exactly_the_threshold_fires():
    """prereg.BOUNDARY_INCLUSIVE. Under binary floats this was order-dependent."""
    obs = {month(1990 + i // 12, i % 12 + 1): "4.4" for i in range(36)}
    for m in (month(1992, 1), month(1992, 2), month(1992, 3)):
        obs[m] = "3.9"
    points = {p.month: p for p in sahm.compute(obs)}

    at_threshold = points[month(1992, 9)]
    assert at_threshold.gap == Decimal("0.50")
    assert at_threshold.fires is True


def test_arithmetic_is_exact_not_binary():
    """The gap is a Decimal, and equals the value a human computes on paper."""
    obs = {month(1990 + i // 12, i % 12 + 1): "4.4" for i in range(36)}
    for m in (month(1992, 1), month(1992, 2), month(1992, 3)):
        obs[m] = "3.9"
    gap = {p.month: p for p in sahm.compute(obs)}[month(1992, 9)].gap

    assert isinstance(gap, Decimal)
    # Exactly one half, not 0.5000000000000004 or 0.4999999999999996.
    assert gap == Decimal("0.50")
    assert gap.compare_total(Decimal("0.50")) == 0  # two decimal places, exactly
    assert prereg.ARITHMETIC == "decimal-exact"


# --- gaps and coverage -------------------------------------------------------


def test_coverage_reports_the_window_not_the_data():
    """A three-year archive must report low coverage, not a clean 1.0."""
    ivs = build_archive(revise_trough_to=None)
    assert replay.coverage(ivs) < prereg.MIN_VINTAGE_COVERAGE


@pytest.mark.parametrize("hole_month", [4, 6, 8])
def test_gaps_never_shorten_the_window(hole_month):
    """A missing month yields fires=None, never an average of fewer months."""
    ivs = [
        i
        for i in build_archive(revise_trough_to=None)
        if i.ref_period_start != month(1992, hole_month)
    ]
    series = replay.vintage_as_of(ivs, dt.date(1996, 1, 1), series_id="UNRATE")
    points = {p.month: p for p in sahm.compute(series)}

    for offset in range(prereg.SAHM_SHORT_WINDOW):
        m = month(1992, hole_month + offset)
        if m in points:
            assert points[m].fires is None, f"{m} was scored across a gap"
