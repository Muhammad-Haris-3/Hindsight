"""First contact with the live ALFRED API. No database, no findings.

This exists because three things in `sources/alfred.py` were written against the
documentation rather than against a response, and each would fail quietly rather
than loudly if it were wrong:

  1. `output_type=1` returns realtime_start/realtime_end on every observation.
  2. `output_type=2` puts each vintage's values in a column we can find.
  3. SAHMREALTIME exists, is fetchable, and covers the preregistered window.

Check 2 has already earned this file's existence once: the first version of
`as_of` guessed the column name from the documentation, guessed wrong, and
returned an empty dict instead of raising. The client now discovers the name.

A quiet failure here would not crash. It would produce an empty vintage, which
reconstructs as "no data was published that day", which reads as a gap in
collection rather than a bug in us. That is exactly the error the project is
about, so it gets checked before anything else runs.

Run:  python scripts/smoke.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from collections import Counter

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

from hindsight import prereg, replay, store
from hindsight.rules import sahm
from hindsight.sources.alfred import Alfred, AlfredError, to_db_rows

OK = "  ok  "
BAD = " FAIL "


def check(label: str, condition: bool, detail: str = "") -> bool:
    print(f"[{OK if condition else BAD}] {label}" + (f" — {detail}" if detail else ""))
    return condition


def main() -> int:
    key = os.environ.get("HINDSIGHT_FRED_API_KEY", "")
    if not key:
        print("HINDSIGHT_FRED_API_KEY is not set in this shell.", file=sys.stderr)
        print("See the README; the key is free and 32 characters.", file=sys.stderr)
        return 2

    print(f"key: {key[:4]}…{key[-4:]} ({len(key)} chars)\n")
    alfred = Alfred()
    results: list[bool] = []

    # --- 1. the archive, as intervals ---------------------------------------
    try:
        intervals = list(alfred.realtime_intervals("UNRATE"))
    except AlfredError as exc:
        print(f"[{BAD}] realtime_intervals raised: {exc}", file=sys.stderr)
        return 1

    results.append(check("output_type=1 returns rows", bool(intervals), f"{len(intervals):,}"))

    vintages = sorted({iv.realtime_start for iv in intervals})
    months = sorted({iv.ref_period_start for iv in intervals})
    results.append(
        check(
            "more vintages than one",
            len(vintages) > 1,
            f"{len(vintages):,} distinct vintage dates, {vintages[0]} … {vintages[-1]}",
        )
    )
    results.append(
        check(
            "reference periods cover the window",
            months[0] <= prereg.WINDOW_START and months[-1] >= prereg.WINDOW_END,
            f"{months[0]} … {months[-1]}",
        )
    )

    restated = Counter(iv.ref_period_start for iv in intervals)
    many = sum(1 for n in restated.values() if n > 1)
    results.append(
        check(
            "some months were restated at least once",
            many > 0,
            f"{many:,} of {len(restated):,} months have more than one vintage",
        )
    )

    # --- 2. the vintage endpoint, and its column naming ----------------------
    probe = vintages[len(vintages) // 2]
    try:
        theirs = alfred.as_of("UNRATE", probe)
    except AlfredError as exc:
        print(f"[{BAD}] as_of raised: {exc}", file=sys.stderr)
        return 1

    results.append(
        check(
            "output_type=2 parses (value column discovered, not assumed)",
            bool(theirs),
            f"vintage {probe} → {len(theirs):,} observations",
        )
    )

    # --- 3. our reconstruction vs theirs, on one vintage ---------------------
    ours = replay.vintage_as_of(intervals, probe, series_id="UNRATE")
    shared = set(theirs) & set(ours)
    worst = max((abs(theirs[m] - ours[m]) for m in shared), default=None)
    results.append(
        check(
            "our reconstruction matches theirs on this vintage",
            bool(shared) and worst is not None and worst <= float(prereg.RECONSTRUCTION_TOL),
            f"{len(shared):,} shared months, worst |diff| {worst}"
            + (f", {len(set(theirs) ^ set(ours))} on one side only" if set(theirs) ^ set(ours) else ""),
        )
    )

    # --- 3b. the store representation loses nothing --------------------------
    # `observations` records when a value started being published and never when
    # it stopped; the end of each interval is derived from the next row. If that
    # derivation is even a day out, every reconstructed vintage is wrong, and
    # wrong in the way that is hardest to see: a value visible one revision too
    # long is indistinguishable from a value nobody revised. Checked here on the
    # whole live archive rather than on a fixture, because the sentinel and the
    # spacing of vintages are the publisher's, not ours.
    rows = [
        (r["series_id"], r["ref_period_start"], r["vintage_date"], r["value"])
        for r in to_db_rows(intervals, frequency="M")
    ]
    round_tripped = store.intervals_from_rows(rows)
    ordered = sorted(intervals, key=lambda iv: (iv.ref_period_start, iv.realtime_start))
    results.append(
        check(
            "the archive survives a round trip through the store's columns",
            round_tripped == ordered,
            f"{len(round_tripped):,} intervals rebuilt from "
            f"(series, period, vintage, value) alone",
        )
    )

    # --- 4. the Gate 2 benchmark exists --------------------------------------
    try:
        bench_vintage = alfred.latest_vintage(prereg.GATE2_BENCHMARK_SERIES)
        bench = alfred.as_of(prereg.GATE2_BENCHMARK_SERIES, bench_vintage)
    except AlfredError as exc:
        bench, bench_vintage = {}, None
        print(f"       {prereg.GATE2_BENCHMARK_SERIES}: {exc}")

    in_window = [m for m in bench if prereg.WINDOW_START <= m <= prereg.WINDOW_END]
    results.append(
        check(
            f"{prereg.GATE2_BENCHMARK_SERIES} is fetchable",
            bool(bench),
            f"vintage {bench_vintage}, {len(bench):,} observations, "
            f"{len(in_window):,} inside the window",
        )
    )

    # --- 5. the rule runs on a real vintage ----------------------------------
    points = [p for p in sahm.compute(ours) if p.fires is not None]
    results.append(
        check(
            "the rule evaluates on real data",
            bool(points),
            f"{sum(p.fires for p in points):,} firings of {len(points):,} scorable months",
        )
    )

    print()
    if all(results):
        print("All checks passed. The client matches the live API.")
        print("Next: scripts/migrate.py, then scripts/ingest.py, then scripts/run_gates.py")
        return 0

    print("Something disagrees with the documentation. Do not ingest yet.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
