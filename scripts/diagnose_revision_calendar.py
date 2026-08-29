"""When did the annual seasonal revision land, and does that explain the split?

**This is diagnosis, not a gate.** It changes no threshold, defines no new
convention, and cannot license the primary outcome. METHODS.md names it as the
one thing that remained available after Gate 2 and Gate 2b both failed:

    "characterising when the annual revision landed in each year, and whether
     that timing accounts for the November/December split."

Gate 2 reads the vintage current on a month's release day. Gate 2b reads the one
after. The failures were disjoint and calendar-locked -- three Decembers under
Gate 2, twenty-five Novembers under Gate 2b -- and that pattern has a prediction
attached, which is why it is worth testing rather than merely describing:

  For reference year Y, both gates read releases in early Y+1.
    * November Y is released in early December Y; Gate 2b then reads the
      January Y+1 release.
    * December Y is released in early January Y+1; Gate 2 reads that release,
      and Gate 2b reads February Y+1.

  So, if the benchmark always reflects the annual revision:
    * revision lands in **January** Y+1  ->  Gate 2's December is fine (it sees
      the revision on release day); Gate 2b's November is not (it reads January
      and sees a revision the benchmark's November value predates).
    * revision lands in **February** Y+1 ->  Gate 2's December fails (release day
      is too early to see it); Gate 2b's November is fine.

  A revision that lands but moves no gap by more than the tolerance produces no
  failure either way, so the prediction is one-directional: **every failure
  should have a revision in the predicted month behind it.** A failure without
  one would falsify the explanation.

The prediction is stated above before the numbers are printed, and the script
reports the years that contradict it as prominently as the years that fit.

Run:  python scripts/diagnose_revision_calendar.py
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

from hindsight import prereg, replay
from hindsight.rules import sahm
from hindsight.sources.alfred import Alfred, RealtimeInterval

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
GATES = OUT / "gates.json"

# The annual seasonal-adjustment revision arrives with a release early in the
# year. The search is confined to that stretch so an unrelated benchmark
# revision later in the year cannot be mistaken for it.
SEASON = (1, 3)  # January .. March


def month_of(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)


def restatements_by_vintage(
    intervals: list[RealtimeInterval], *, series_id: str = "UNRATE"
) -> dict[dt.date, dict]:
    """For each vintage, how much previously-published history it rewrote.

    A restatement is a reference month whose value differs from the value the
    *previous* vintage carried for it. New months are not restatements: a month
    published for the first time has nothing to differ from.
    """
    vintages = sorted({iv.realtime_start for iv in intervals if iv.series_id == series_id})
    out: dict[dt.date, dict] = {}

    previous: dict[dt.date, float] | None = None
    for v in vintages:
        current = replay.vintage_as_of(intervals, v, series_id=series_id)
        if previous is not None:
            changed = [
                m for m in current
                if m in previous and Decimal(str(current[m])) != Decimal(str(previous[m]))
            ]
            out[v] = {
                "n_restated": len(changed),
                "earliest_restated": min(changed) if changed else None,
                "latest_restated": max(changed) if changed else None,
            }
        else:
            out[v] = {"n_restated": 0, "earliest_restated": None, "latest_restated": None}
        previous = current

    return out


def gap_on(
    intervals: list[RealtimeInterval], month: dt.date, as_of: dt.date
) -> Decimal | None:
    vintage = replay.vintage_as_of(intervals, as_of, series_id="UNRATE")
    point = {p.month: p for p in sahm.compute(vintage)}.get(month)
    return None if point is None else point.gap


def recorded_failures() -> tuple[set[dt.date], set[dt.date]]:
    """The months each gate actually failed on, read from the recorded run.

    Read rather than recomputed on purpose: the question is whether the timing
    explains *the failures that were published*, not a fresh set that might have
    moved since.
    """
    if not GATES.exists():
        return set(), set()
    payload = json.loads(GATES.read_text(encoding="utf-8"))
    by_gate = {r["gate"]: r for r in payload.get("results", [])}

    def months(gate: str) -> set[dt.date]:
        return {
            dt.date.fromisoformat(f["month"])
            for f in by_gate.get(gate, {}).get("failures", [])
            if "month" in f
        }

    return months("rule_reproduces"), months("rule_reproduces_offset")


def main() -> int:
    alfred = Alfred()
    intervals = list(alfred.realtime_intervals("UNRATE"))
    vintages = sorted({iv.realtime_start for iv in intervals})
    restated = restatements_by_vintage(intervals)
    first_pub = replay.first_publication_dates(intervals, series_id="UNRATE")

    gate2_failed, gate2b_failed = recorded_failures()
    if not gate2_failed and not gate2b_failed:
        print("NOTE: artifacts/gates.json holds no failing months to explain.\n")

    rows: list[dict] = []
    for year in range(prereg.WINDOW_START.year, prereg.WINDOW_END.year + 1):
        nov, dec = dt.date(year, 11, 1), dt.date(year, 12, 1)
        if nov not in first_pub or dec not in first_pub:
            continue

        # The releases each gate reads, for this year's November and December.
        nov_release = first_pub[nov]
        dec_release = first_pub[dec]
        after_dec = next((v for v in vintages if v > dec_release), None)
        nov_offset = dec_release  # gate 2b's vintage for November

        # The largest restatement carried by any release in Jan..Mar of Y+1.
        season = [
            v for v in vintages
            if v.year == year + 1 and SEASON[0] <= v.month <= SEASON[1]
        ]
        if season:
            landed = max(season, key=lambda v: restated[v]["n_restated"])
            n_restated = restated[landed]["n_restated"]
            earliest = restated[landed]["earliest_restated"]
        else:
            landed, n_restated, earliest = None, 0, None

        # How much the following release moved each month's gap. This is the
        # part that decides whether a revision could have caused a failure at
        # all: one that moves no gap cannot.
        nov_moved = _delta(gap_on(intervals, nov, nov_release),
                           gap_on(intervals, nov, nov_offset))
        dec_moved = _delta(gap_on(intervals, dec, dec_release),
                           gap_on(intervals, dec, after_dec) if after_dec else None)

        rows.append(
            {
                "year": year,
                "landed": landed,
                "landed_month": None if landed is None else landed.month,
                "n_restated": n_restated,
                "earliest_restated": earliest,
                "nov_gap_moved": nov_moved,
                "dec_gap_moved": dec_moved,
                "gate2_dec_failed": dec in gate2_failed,
                "gate2b_nov_failed": nov in gate2b_failed,
            }
        )

    _report(rows)
    _write(rows)
    return 0


def _delta(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    return None if a is None or b is None else b - a


def _fmt(x) -> str:
    return "  ." if x is None else f"{x:>4}"


def _report(rows: list[dict]) -> None:
    print(f"\n{'UNRATE annual restatement calendar':^92}")
    print(f"{'the largest restatement carried by any Jan-Mar release, per reference year':^92}\n")
    print(
        "  year  landed       mo  months   back to     nov gap    dec gap   "
        "G2 dec  G2b nov"
    )
    print("  " + "-" * 88)
    for r in rows:
        print(
            f"  {r['year']}  {str(r['landed'] or '-'):<11}"
            f"{r['landed_month'] or '-':>3}"
            f"{r['n_restated']:>8}   "
            f"{str(r['earliest_restated'] or '-'):<11}"
            f"{_fmt(r['nov_gap_moved']):>8}   {_fmt(r['dec_gap_moved']):>8}   "
            f"{'FAIL' if r['gate2_dec_failed'] else '  . ':>6}  "
            f"{'FAIL' if r['gate2b_nov_failed'] else '  . ':>7}"
        )

    print("\n\n  Landing month against gate failures")
    print("  " + "-" * 88)
    tab = Counter(
        (r["landed_month"], r["gate2_dec_failed"], r["gate2b_nov_failed"]) for r in rows
    )
    print("  landing month   G2 dec fails   G2b nov fails   years")
    for (mo, g2, g2b), n in sorted(tab.items(), key=lambda kv: (kv[0][0] or 0,)):
        print(
            f"  {str(mo or '-'):<15} {'yes' if g2 else 'no':<14} "
            f"{'yes' if g2b else 'no':<15} {n}"
        )

    # The prediction, tested. Stated in this file's docstring before any of the
    # numbers above existed on screen.
    print("\n\n  The prediction, tested")
    print("  " + "-" * 88)
    g2_rows = [r for r in rows if r["gate2_dec_failed"]]
    g2b_rows = [r for r in rows if r["gate2b_nov_failed"]]

    g2_fit = [r for r in g2_rows if r["landed_month"] == 2]
    g2b_fit = [r for r in g2b_rows if r["landed_month"] == 1]

    print(
        f"  Gate 2  December failures with a February landing:  "
        f"{len(g2_fit)}/{len(g2_rows)}"
    )
    print(
        f"  Gate 2b November failures with a January landing:   "
        f"{len(g2b_fit)}/{len(g2b_rows)}"
    )

    contradictions = [r for r in g2_rows if r["landed_month"] != 2] + [
        r for r in g2b_rows if r["landed_month"] != 1
    ]
    if contradictions:
        print("\n  Years the explanation does NOT cover:")
        for r in contradictions:
            print(
                f"    {r['year']}: landed month {r['landed_month']}, "
                f"{r['n_restated']} months restated, "
                f"G2 dec {'FAIL' if r['gate2_dec_failed'] else 'ok'}, "
                f"G2b nov {'FAIL' if r['gate2b_nov_failed'] else 'ok'}"
            )
    else:
        print("\n  No failure is left unexplained by the landing month.")

    quiet = [
        r for r in rows
        if not r["gate2_dec_failed"] and not r["gate2b_nov_failed"]
    ]
    print(
        f"\n  {len(quiet)} of {len(rows)} years produced no failure in either gate. "
        "A revision\n  that moves no gap past the tolerance cannot cause one, so these\n"
        "  are consistent with the explanation rather than evidence against it."
    )
    print(
        "\n  This is diagnosis. It defines no convention, and no gate verdict "
        "changes.\n"
    )


def _write(rows: list[dict]) -> None:
    OUT.mkdir(exist_ok=True)
    path = OUT / "revision_calendar.json"
    path.write_text(
        json.dumps(
            {
                "note": (
                    "Diagnosis of the Gate 2 / Gate 2b failure pattern. Post-hoc "
                    "by construction, gates nothing, defines no convention. See "
                    "METHODS.md."
                ),
                "generated_from": "UNRATE vintages, ALFRED",
                "years": [
                    {
                        k: (v.isoformat() if isinstance(v, dt.date)
                            else str(v) if isinstance(v, Decimal) else v)
                        for k, v in r.items()
                    }
                    for r in rows
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  written to {path.relative_to(ROOT)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
