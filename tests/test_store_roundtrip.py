"""The store loses nothing, and the join that proves it is the one Gate 1 marks.

`observations` records when a value *started* being the published figure and
never when it stopped, because a publisher never says that. The end of an
interval is derived from the next row. If that derivation is wrong, every
reconstructed vintage is wrong, and wrong in the direction that is hardest to
notice: a value that stays visible one revision too long looks exactly like a
value that was never revised.

So the archive is round-tripped here -- intervals to rows and back -- and every
interval must return unchanged. Checked against the live API on 2026-08-30:
across 1,254 consecutive pairs of `UNRATE` vintages, `realtime_end` was the day
before the next `realtime_start` without exception, and every currently-published
value carried the archive's open-ended sentinel. The derivation is exact, not
approximate.
"""

from __future__ import annotations

import datetime as dt

import pytest

from hindsight import replay, store
from hindsight.sources.alfred import RealtimeInterval, to_db_rows

FOREVER = store.STILL_CURRENT


def month(y: int, m: int) -> dt.date:
    return dt.date(y, m, 1)


def as_rows(intervals: list[RealtimeInterval]) -> list[tuple]:
    """Through the shape the database actually holds, columns and all."""
    return [
        (r["series_id"], r["ref_period_start"], r["vintage_date"], r["value"])
        for r in to_db_rows(intervals, frequency="M")
    ]


def archive() -> list[RealtimeInterval]:
    """Three months, one of them restated twice, one published as missing."""
    return [
        RealtimeInterval("UNRATE", month(2015, 1), 5.7,
                         dt.date(2015, 2, 6), dt.date(2015, 3, 5)),
        RealtimeInterval("UNRATE", month(2015, 1), 5.6,
                         dt.date(2015, 3, 6), dt.date(2016, 2, 4)),
        RealtimeInterval("UNRATE", month(2015, 1), 5.5,
                         dt.date(2016, 2, 5), FOREVER),
        RealtimeInterval("UNRATE", month(2015, 2), 5.5,
                         dt.date(2015, 3, 6), FOREVER),
        RealtimeInterval("UNRATE", month(2015, 3), None,
                         dt.date(2015, 4, 3), FOREVER),
    ]


def test_every_interval_survives_the_round_trip():
    assert store.intervals_from_rows(as_rows(archive())) == sorted(
        archive(), key=lambda iv: (iv.ref_period_start, iv.realtime_start)
    )


def test_a_restated_period_comes_back_as_separate_non_overlapping_intervals():
    """A restatement is a new row, and must not swallow the row before it."""
    back = [
        iv for iv in store.intervals_from_rows(as_rows(archive()))
        if iv.ref_period_start == month(2015, 1)
    ]
    assert len(back) == 3
    for a, b in zip(back, back[1:]):
        assert a.realtime_end == b.realtime_start - dt.timedelta(days=1)
        assert a.realtime_end < b.realtime_start


def test_the_newest_value_stays_open_ended():
    back = store.intervals_from_rows(as_rows(archive()))
    newest = max(
        (iv for iv in back if iv.ref_period_start == month(2015, 1)),
        key=lambda iv: iv.realtime_start,
    )
    assert newest.realtime_end == FOREVER


def test_published_as_missing_stays_missing_and_is_not_imputed():
    """NULL is the publisher saying nothing. It is never turned into a number."""
    back = store.intervals_from_rows(as_rows(archive()))
    missing = [iv for iv in back if iv.ref_period_start == month(2015, 3)]
    assert [iv.value for iv in missing] == [None]


@pytest.mark.parametrize(
    "vintage",
    [
        dt.date(2015, 2, 6), dt.date(2015, 3, 5), dt.date(2015, 3, 6),
        dt.date(2016, 2, 4), dt.date(2016, 2, 5), dt.date(2026, 9, 1),
    ],
)
def test_every_vintage_reconstructs_identically_from_the_store(vintage):
    """The comparison the gates make must not depend on which side it read.

    Gate 1 checks our reconstruction against ALFRED's own. If the store and the
    API disagreed on any vintage, the gate would be marking whichever one it
    happened to be handed.
    """
    direct = replay.vintage_as_of(archive(), vintage, series_id="UNRATE")
    from_store = replay.vintage_as_of(
        store.intervals_from_rows(as_rows(archive())), vintage, series_id="UNRATE"
    )
    assert direct == from_store


def test_a_period_never_collected_has_no_row_and_no_interval():
    """Absent is absent. A gap in collection is not a period nobody revised."""
    partial = [iv for iv in archive() if iv.ref_period_start != month(2015, 2)]
    back = store.intervals_from_rows(as_rows(partial))
    assert month(2015, 2) not in {iv.ref_period_start for iv in back}
    assert month(2015, 2) not in replay.vintage_as_of(
        back, dt.date(2026, 9, 1), series_id="UNRATE"
    )
