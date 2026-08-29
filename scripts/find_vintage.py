"""Which vintage does SAHMREALTIME actually use?

For a given reference month, try every vintage UNRATE has ever had, and report
which ones reproduce FRED's published real-time gap for that month. Then say how
that vintage relates to the month's own release date.

This replaces guessing at the definition with reading it off the data.

Run:  python scripts/find_vintage.py 1981-12 1976-12 1977-12 1980-12
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


def main() -> int:
    months = [dt.date.fromisoformat(a + "-01") for a in (sys.argv[1:] or ["1981-12"])]

    alfred = Alfred()
    intervals = list(alfred.realtime_intervals("UNRATE"))
    theirs = alfred.as_of(
        prereg.GATE2_BENCHMARK_SERIES,
        alfred.latest_vintage(prereg.GATE2_BENCHMARK_SERIES),
    )

    vintages = sorted({iv.realtime_start for iv in intervals})
    first_pub = replay.first_publication_dates(intervals, series_id="UNRATE")

    for month in months:
        target = theirs.get(month)
        release = first_pub[month]
        print(f"\n=== {month} ".ljust(70, "="))
        print(f"  released {release}   SAHMREALTIME {target}")

        if target is None:
            print("  not in the benchmark")
            continue
        target = Decimal(str(target))

        matches: list[tuple[dt.date, Decimal]] = []
        for v in vintages:
            if v < release:
                continue  # the month did not exist yet
            series = replay.vintage_as_of(intervals, v, series_id="UNRATE")
            point = {p.month: p for p in sahm.compute(series)}.get(month)
            if point is None or point.gap is None:
                continue
            if point.gap == target:
                matches.append((v, point.gap))

        if not matches:
            print("  NO vintage reproduces it. The difference is not the vintage.")
            continue

        first_match = matches[0][0]
        lag_days = (first_match - release).days
        n_releases = sum(1 for v in vintages if release < v <= first_match)
        print(f"  {len(matches)} vintage(s) reproduce it; earliest {first_match}")
        print(f"  that is {lag_days} days after release, {n_releases} vintage(s) later")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
