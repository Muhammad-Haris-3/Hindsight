"""Run both preregistered gates and record the result.

Exit status is the gate verdict. A failing gate must fail the job: a pipeline
that records "gate failed" and then carries on to compute the primary outcome
has a preregistration in name only.

Where the intervals come from is itself recorded. Gate 1 is described in the
preregistration as testing "our storage and our joins", which it only does if
the intervals it checks came back out of the store. Reading them from the API
instead is a valid run of the gate's arithmetic and an invalid run of its
premise, and the difference is invisible in the verdict -- so `gates.json`
carries `intervals_from`, and no reader has to take the source on trust.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

from hindsight import gates, prereg, store
from hindsight.sources.alfred import Alfred

OUT = Path(__file__).resolve().parents[1] / "artifacts"


def load_intervals(alfred: Alfred, source: str) -> tuple[list, str]:
    """Return the intervals and the name of where they actually came from.

    `auto` prefers the store, because that is the path the pipeline uses and the
    path Gate 1 claims to test. It falls back to the API only when no DSN is
    configured, and says so rather than pretending.
    """
    dsn = os.environ.get("HINDSIGHT_READER_DSN") or os.environ.get("HINDSIGHT_WRITER_DSN")

    if source == "store" or (source == "auto" and dsn):
        if not dsn:
            raise SystemExit(
                "--source store needs HINDSIGHT_READER_DSN or HINDSIGHT_WRITER_DSN. "
                "Refusing to fall back to the API: the fallback would pass Gate 1 "
                "without testing the storage it claims to test."
            )
        return store.read_intervals(dsn, "UNRATE"), "store"

    return list(alfred.realtime_intervals("UNRATE")), "alfred-api"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        choices=("auto", "store", "api"),
        default="auto",
        help="where the gates read intervals from. Recorded in gates.json.",
    )
    args = ap.parse_args()

    alfred = Alfred()
    OUT.mkdir(exist_ok=True)

    intervals, source = load_intervals(alfred, args.source)
    print(f"held: {len(intervals)} intervals for UNRATE (from {source})")
    if source != "store":
        print(
            "NOTE: intervals came from the API, not the store. Gate 1 therefore "
            "marks the reconstruction but not the round-trip through Postgres. "
            "Recorded as such in gates.json.",
            file=sys.stderr,
        )

    results = [
        gates.gate1_capture_is_faithful(intervals, alfred, series_id="UNRATE"),
        gates.gate2_rule_reproduces_benchmark(intervals, alfred),
        gates.gate2b_under_benchmark_convention(intervals, alfred),
    ]

    for r in results:
        print(r.summary())
        for f in r.failures[:10]:
            print("   ", json.dumps(f))

    (OUT / "gates.json").write_text(
        json.dumps(
            {
                "freeze_date": prereg.FREEZE_DATE.isoformat(),
                "intervals_from": source,
                "results": [
                    {
                        "gate": r.gate,
                        "passed": r.passed,
                        "post_hoc": r.gate == "rule_reproduces_offset",
                        "n_checked": r.n_checked,
                        "n_failed": r.n_failed,
                        "max_abs_diff": None if r.max_abs_diff is None else str(r.max_abs_diff),
                        "failures": r.failures,
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Gate 2b is post-hoc and never gates the outcome by itself; Gate 2's
    # verdict is the one the preregistration binds. Recorded, not decisive.
    binding = [r for r in results if r.gate != "rule_reproduces_offset"]

    if not all(r.passed for r in binding):
        print("\nA gate failed. The primary outcome is not computed.", file=sys.stderr)
        return 1

    print("\nBoth gates passed. The primary outcome may now be computed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
