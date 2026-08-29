"""Why do our real-time gaps disagree with SAHMREALTIME on exactly three months?

Not a fix. A look at the arithmetic behind one disagreeing month, printed beside
the arithmetic behind an agreeing one, so the difference has to explain itself.

Run:  python scripts/diagnose_gate2.py 1981-12
"""

from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

from hindsight import prereg, replay
from hindsight.rules import sahm
from hindsight.sources.alfred import Alfred


def show(month: dt.date, intervals, theirs: dict, alfred: Alfred) -> None:
    first_pub = replay.first_publication_dates(intervals, series_id="UNRATE")
    pub = first_pub[month]

    # (A) our definition: the vintage current on the day `month` was published
    vintage = replay.vintage_as_of(intervals, pub, series_id="UNRATE")
    a = {p.month: p for p in sahm.compute(vintage)}[month]

    # (B) an alternative: a series built from each month's FIRST PRINT, which is
    # not any single vintage that ever existed
    first_prints: dict[dt.date, Decimal] = {}
    for iv in intervals:
        if iv.value is None:
            continue
        m = iv.ref_period_start
        if m not in first_prints or iv.realtime_start < first_pub[m]:
            if iv.realtime_start == first_pub[m]:
                first_prints[m] = Decimal(str(iv.value))
    for iv in intervals:
        if iv.value is not None and iv.realtime_start == first_pub[iv.ref_period_start]:
            first_prints[iv.ref_period_start] = Decimal(str(iv.value))
    b_series = {m: v for m, v in first_prints.items() if m <= month}
    b = {p.month: p for p in sahm.compute(b_series)}.get(month)

    theirs_v = theirs.get(month)

    print(f"\n=== {month} ".ljust(64, "="))
    print(f"first published        {pub}")
    print(f"SAHMREALTIME           {theirs_v}")
    print(f"(A) vintage-at-release {a.gap}   avg {a.short_avg}  min {a.prior_min}")
    if b is not None:
        print(f"(B) first-print series {b.gap}   avg {b.short_avg}  min {b.prior_min}")

    # which month supplied the minimum, and what each definition thinks it was
    idx = sorted(m for m in vintage if m < month)
    lookback = idx[-prereg.SAHM_LOOKBACK :]
    print(f"\n  lookback {lookback[0]} .. {lookback[-1]}")
    print("  month       vintage-at-release   first-print   changed")
    for m in lookback:
        v = vintage.get(m)
        fp = first_prints.get(m)
        mark = "" if v is None or fp is None or Decimal(str(v)) == fp else "  <-- revised"
        print(f"  {m}  {str(v):>12}   {str(fp):>12}{mark}")


def main() -> int:
    months = [dt.date.fromisoformat(a + "-01") for a in (sys.argv[1:] or ["1981-12"])]

    alfred = Alfred()
    intervals = list(alfred.realtime_intervals("UNRATE"))
    bench_vintage = alfred.latest_vintage(prereg.GATE2_BENCHMARK_SERIES)
    theirs = alfred.as_of(prereg.GATE2_BENCHMARK_SERIES, bench_vintage)

    for m in months:
        show(m, intervals, theirs, alfred)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
