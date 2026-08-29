"""Replaying a rule against what was knowable, versus what is known.

This module holds the single comparison the project exists to make. It is short
on purpose: the difficult part is upstream, in refusing to let a value that did
not exist yet reach the rule.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from hindsight import prereg
from hindsight.rules import sahm
from hindsight.sources.alfred import RealtimeInterval


@dataclass(frozen=True)
class Flip:
    month: dt.date
    fired_in_real_time: bool
    fires_now: bool
    gap_then: float | None
    gap_now: float | None

    @property
    def direction(self) -> str:
        """Whether hindsight invented the signal or erased it."""
        return "appeared" if self.fires_now else "vanished"


def vintage_as_of(
    intervals: Iterable[RealtimeInterval], vintage: dt.date, *, series_id: str
) -> dict[dt.date, float]:
    """Reconstruct one vintage from stored real-time intervals.

    A value is visible on `vintage` iff realtime_start <= vintage <= realtime_end.
    This is the only place the archive is collapsed to a single view, and it is
    the function Gate 1 marks against ALFRED's own answer.
    """
    out: dict[dt.date, float] = {}
    for iv in intervals:
        if iv.series_id != series_id or iv.value is None:
            continue
        if iv.realtime_start <= vintage <= iv.realtime_end:
            out[iv.ref_period_start] = iv.value
    return out


def first_publication_dates(
    intervals: Iterable[RealtimeInterval], *, series_id: str
) -> dict[dt.date, dt.date]:
    """For each reference period, the day it was first published."""
    first: dict[dt.date, dt.date] = {}
    for iv in intervals:
        if iv.series_id != series_id:
            continue
        m = iv.ref_period_start
        if m not in first or iv.realtime_start < first[m]:
            first[m] = iv.realtime_start
    return first


def flips(
    intervals: Iterable[RealtimeInterval],
    *,
    series_id: str = "UNRATE",
    freeze: dt.date | None = None,
) -> list[Flip]:
    """The primary outcome: months where real-time and today disagree.

    fire_rt(m) is computed from the vintage current on the day m was first
    published -- not from today's series truncated at month m, which is the
    mistake the whole project is about. A truncated modern series still carries
    every later correction to *earlier* months, and those feed the twelve-month
    minimum the rule subtracts.
    """
    intervals = list(intervals)
    freeze = freeze or prereg.FREEZE_DATE
    first_pub = first_publication_dates(intervals, series_id=series_id)

    now_series = vintage_as_of(intervals, freeze, series_id=series_id)
    now = {p.month: p for p in sahm.compute(now_series)}

    out: list[Flip] = []
    for month in sorted(first_pub):
        if not (prereg.WINDOW_START <= month <= prereg.WINDOW_END):
            continue

        then_series = vintage_as_of(intervals, first_pub[month], series_id=series_id)
        then = {p.month: p for p in sahm.compute(then_series)}

        a, b = then.get(month), now.get(month)
        if a is None or b is None or a.fires is None or b.fires is None:
            # Not computable in one view or the other. Counted against coverage,
            # never silently counted as agreement.
            continue
        if a.fires != b.fires:
            out.append(Flip(month, a.fires, b.fires, a.gap, b.gap))

    return out


def coverage(
    intervals: Iterable[RealtimeInterval], *, series_id: str = "UNRATE"
) -> float:
    """Fraction of window months for which a first-publication vintage exists.

    Published alongside every flip count. A flip rate computed over half the
    window is not a smaller finding, it is a different one.
    """
    first_pub = first_publication_dates(intervals, series_id=series_id)
    have = sum(
        1 for m in first_pub if prereg.WINDOW_START <= m <= prereg.WINDOW_END
    )
    span = (prereg.WINDOW_END.year - prereg.WINDOW_START.year) * 12 + (
        prereg.WINDOW_END.month - prereg.WINDOW_START.month
    ) + 1
    return have / span
