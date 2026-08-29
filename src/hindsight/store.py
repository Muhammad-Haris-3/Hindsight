"""Reading the append-only store back as real-time intervals.

The store has no `realtime_end` column, and that is deliberate rather than an
omission: an end date is not something a publisher ever says. A value is current
until a different value is published for the same period, so the interval it was
current for is *derived* from the next row, never recorded. Recording it would
create a second place where "when was this true" lives, and the two would drift.

That derivation is the join Gate 1 exists to mark. `PREREGISTRATION.md` describes
Gate 1 as testing "our storage and our joins" -- so the intervals it checks have
to have come back out of the store, not straight from the API. Until this module
existed they came straight from the API, and Gate 1 marked a path the pipeline
does not use. See METHODS.md, *What Gate 1 did and did not test*.

`intervals_from_rows` is a pure function over rows and is tested offline, by
round-tripping the archive through `to_db_rows` and requiring every interval
back unchanged. The database query around it is a `SELECT` and nothing else.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from hindsight.sources.alfred import ARCHIVE_END, RealtimeInterval

# The archive's own sentinel for "until further notice". Checked against the
# live API: every currently-published value carries exactly this end date.
STILL_CURRENT = dt.date.fromisoformat(ARCHIVE_END)

SELECT = """
SELECT series_id, ref_period_start, vintage_date, value
  FROM observations
 WHERE series_id = %s
 ORDER BY ref_period_start, vintage_date
"""


def intervals_from_rows(
    rows: Iterable[tuple[str, dt.date, dt.date, object]],
) -> list[RealtimeInterval]:
    """Rebuild real-time intervals from append-only rows.

    Each row is `(series_id, ref_period_start, vintage_date, value)`. A value is
    current from its own vintage date until the day before the next vintage of
    the same period; the newest carries the archive's open-ended sentinel.

    Rows are grouped per period, so a period restated ten times yields ten
    non-overlapping intervals covering the whole span with no gap between them.
    """
    by_period: dict[tuple[str, dt.date], list[tuple[dt.date, object]]] = defaultdict(list)
    for series_id, period, vintage, value in rows:
        by_period[(series_id, period)].append((vintage, value))

    out: list[RealtimeInterval] = []
    for (series_id, period), versions in by_period.items():
        versions.sort(key=lambda v: v[0])
        for i, (vintage, value) in enumerate(versions):
            if i + 1 < len(versions):
                end = versions[i + 1][0] - dt.timedelta(days=1)
            else:
                end = STILL_CURRENT
            out.append(
                RealtimeInterval(
                    series_id=series_id,
                    ref_period_start=period,
                    # A period published as missing is stored NULL and stays
                    # None. It is not the same as a period we never collected,
                    # which has no row at all, and the two are never merged.
                    value=None if value is None else float(value),
                    realtime_start=vintage,
                    realtime_end=end,
                )
            )

    out.sort(key=lambda iv: (iv.ref_period_start, iv.realtime_start))
    return out


def read_intervals(dsn: str, series_id: str) -> list[RealtimeInterval]:
    """Read one series out of the store as real-time intervals.

    `psycopg` is an optional dependency: the offline suite -- which is all of it
    except the gates -- must run on a machine with no driver and no database.
    """
    import psycopg  # imported here so the offline suite never needs it

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(SELECT, (series_id,)).fetchall()
    return intervals_from_rows(rows)
