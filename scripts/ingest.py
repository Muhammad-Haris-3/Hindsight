"""Append every vintage ALFRED holds for the preregistered series.

Idempotent by construction rather than by checking: a repeat row violates the
primary key, so `ON CONFLICT DO NOTHING` appends new vintages and leaves existing
rows untouched. There is no code path here that updates one.
"""

from __future__ import annotations

import json
import os

import psycopg

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

from hindsight import prereg
from hindsight.sources.alfred import Alfred, to_db_rows

FREQUENCY = {"UNRATE": "M", "PAYEMS": "M", "GDPC1": "Q", "INDPRO": "M", "RSAFS": "M"}

INSERT = """
INSERT INTO observations
    (series_id, ref_period_start, ref_period_end, vintage_date, value,
     run_label, ingest_run_id)
VALUES (%(series_id)s, %(ref_period_start)s, %(ref_period_end)s,
        %(vintage_date)s, %(value)s, %(run_label)s, %(run_id)s)
ON CONFLICT (series_id, ref_period_start, vintage_date) DO NOTHING
"""


def main() -> int:
    alfred = Alfred()
    dsn = os.environ["HINDSIGHT_WRITER_DSN"]

    with psycopg.connect(dsn) as conn:
        run_id = conn.execute(
            "INSERT INTO ingest_runs (source) VALUES ('alfred') RETURNING run_id"
        ).fetchone()[0]
        conn.commit()

        appended = seen = 0
        try:
            for series_id, role in prereg.SERIES.items():
                conn.execute(
                    "INSERT INTO series (series_id, source, title, units, frequency, role)"
                    " VALUES (%s,'alfred',%s,'',%s,%s) ON CONFLICT DO NOTHING",
                    (series_id, series_id, FREQUENCY[series_id], role),
                )

                intervals = list(alfred.realtime_intervals(series_id))
                seen += len({iv.realtime_start for iv in intervals})

                for row in to_db_rows(intervals, frequency=FREQUENCY[series_id]):
                    cur = conn.execute(INSERT, {**row, "run_id": run_id})
                    appended += cur.rowcount
                conn.commit()
                print(f"{series_id}: {len(intervals)} intervals")

        except Exception as exc:
            # A failed run is recorded, not rolled back into invisibility. A gap
            # in collection must never read as a period nobody revised anything.
            conn.rollback()
            conn.execute(
                "UPDATE ingest_runs SET status='failed', finished_at=now(),"
                " detail=%s WHERE run_id=%s",
                (json.dumps({"error": str(exc)[:500]}), run_id),
            )
            conn.commit()
            raise

        conn.execute(
            "UPDATE ingest_runs SET status='ok', finished_at=now(),"
            " rows_appended=%s, vintages_seen=%s WHERE run_id=%s",
            (appended, seen, run_id),
        )
        conn.commit()
        print(f"appended {appended} rows across {seen} vintages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
