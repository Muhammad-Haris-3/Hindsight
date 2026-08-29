"""Compute the primary outcome. Once.

This script enforces two things the preregistration promises but prose cannot:

  1. **Gates first.** It refuses to run unless artifacts/gates.json records both
     gates passing, at the preregistered freeze date. A pipeline that computes a
     finding after a failed gate has a preregistration in name only.

  2. **The stopping rule.** The outcome is computed once. If artifacts/outcome.json
     already exists, this refuses to overwrite it unless --recompute is passed
     with a --reason, and the previous result is kept alongside the new one. The
     easiest way to launder a disappointing count is to quietly run it again with
     a different constant; that path is closed by making the second run leave
     evidence.

Run:  python scripts/outcome.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

from hindsight import prereg, replay
from hindsight.sources.alfred import Alfred

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
GATES = OUT / "gates.json"
OUTCOME = OUT / "outcome.json"


def refuse(message: str) -> int:
    print(f"\nREFUSED: {message}", file=sys.stderr)
    return 2


def check_gates() -> str | None:
    """Return a refusal reason, or None if the gates permit a finding."""
    if not GATES.exists():
        return "artifacts/gates.json does not exist. Run scripts/run_gates.py first."

    payload = json.loads(GATES.read_text(encoding="utf-8"))

    if payload.get("freeze_date") != prereg.FREEZE_DATE.isoformat():
        return (
            f"gates were run at freeze date {payload.get('freeze_date')}, but the "
            f"preregistration fixes {prereg.FREEZE_DATE}. Re-run the gates."
        )

    results = {r["gate"]: r for r in payload.get("results", [])}
    for name in ("capture_faithful", "rule_reproduces"):
        r = results.get(name)
        if r is None:
            return f"gate {name!r} was never run."
        if not r["passed"]:
            return (
                f"gate {name!r} failed ({r['n_failed']}/{r['n_checked']}). "
                "The preregistration says the outcome is not computed."
            )
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()

    if (reason := check_gates()) is not None:
        return refuse(reason)

    if OUTCOME.exists() and not args.recompute:
        return refuse(
            "artifacts/outcome.json already exists. The preregistration says the "
            "primary outcome is computed once. Pass --recompute --reason '...' if "
            "there is a real reason; the previous result will be kept."
        )
    if args.recompute and not args.reason.strip():
        return refuse("--recompute requires --reason, which is recorded in the output.")

    alfred = Alfred()
    intervals = list(alfred.realtime_intervals("UNRATE"))
    flips = replay.flips(intervals, series_id="UNRATE")
    cover = replay.coverage(intervals, series_id="UNRATE")

    span = (prereg.WINDOW_END.year - prereg.WINDOW_START.year) * 12 + (
        prereg.WINDOW_END.month - prereg.WINDOW_START.month
    ) + 1

    vanished = [f for f in flips if f.direction == "vanished"]
    appeared = [f for f in flips if f.direction == "appeared"]

    print(f"\nwindow      {prereg.WINDOW_START} .. {prereg.WINDOW_END}  ({span} months)")
    print(f"coverage    {cover:.4f}  (floor {prereg.MIN_VINTAGE_COVERAGE})")
    print(f"flips       {len(flips)}  ({len(flips) / span:.4%} of months)")
    print(f"  vanished  {len(vanished)}  fired then, does not fire now")
    print(f"  appeared  {len(appeared)}  did not fire then, fires now")

    if flips:
        print("\n  month       then    now     gap_then  gap_now")
        for f in flips:
            print(
                f"  {f.month}  "
                f"{'FIRE' if f.fired_in_real_time else '  - '}    "
                f"{'FIRE' if f.fires_now else '  - '}    "
                f"{f.gap_then:>7}   {f.gap_now:>7}"
            )
    else:
        print("\n  No month decides differently. That is the finding.")

    previous = (
        json.loads(OUTCOME.read_text(encoding="utf-8")) if OUTCOME.exists() else None
    )
    OUT.mkdir(exist_ok=True)
    OUTCOME.write_text(
        json.dumps(
            {
                "computed_at": dt.datetime.now(dt.UTC).isoformat(),
                "freeze_date": prereg.FREEZE_DATE.isoformat(),
                "window": [
                    prereg.WINDOW_START.isoformat(),
                    prereg.WINDOW_END.isoformat(),
                ],
                "months_in_window": span,
                "coverage": round(cover, 6),
                "flip_count": len(flips),
                "flip_rate": round(len(flips) / span, 6),
                "flips": [
                    {
                        "month": f.month.isoformat(),
                        "fired_in_real_time": f.fired_in_real_time,
                        "fires_now": f.fires_now,
                        "gap_then": str(f.gap_then),
                        "gap_now": str(f.gap_now),
                    }
                    for f in flips
                ],
                "recomputed": bool(args.recompute),
                "recompute_reason": args.reason or None,
                "superseded": previous,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwritten to {OUTCOME.relative_to(ROOT)}")

    if cover < prereg.MIN_VINTAGE_COVERAGE:
        print(
            f"\nNOTE: coverage {cover:.4f} is below the preregistered floor "
            f"{prereg.MIN_VINTAGE_COVERAGE}. The count above is reported with that "
            "caveat attached, not without it.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
