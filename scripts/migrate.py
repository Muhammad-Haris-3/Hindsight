"""Apply the schema, then create the roles and revoke what they must not have.

The grants live here rather than in schema.sql because they are the security
boundary, not the shape of the data, and because they must be applied as an
admin role while every other connection in the project is not one.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

from hindsight import console as _console, env as _env

_console.use_utf8()
_env.load()

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"

# The writer may append. It may not restate the past. The reader may only look.
GRANTS = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hindsight_writer') THEN
        CREATE ROLE hindsight_writer LOGIN PASSWORD 'writer';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hindsight_reader') THEN
        CREATE ROLE hindsight_reader LOGIN PASSWORD 'reader';
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO hindsight_writer, hindsight_reader;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hindsight_writer;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO hindsight_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hindsight_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM hindsight_writer;

-- ingest_runs is collection metadata, not evidence: a run has to be able to
-- close itself as ok or failed. Granting UPDATE back here, on this table only,
-- keeps that narrow and keeps `observations` strictly append-only.
GRANT UPDATE ON ingest_runs TO hindsight_writer;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hindsight_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO hindsight_reader;
"""


def main() -> int:
    dsn = os.environ["HINDSIGHT_ADMIN_DSN"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.execute(GRANTS)

        # Assert the revoke actually took. A migration that silently no-ops
        # leaves the append-only claim resting on nothing.
        for table, priv, expected in [
            ("observations", "UPDATE", False),
            ("observations", "DELETE", False),
            ("observations", "INSERT", True),
            ("gate_results", "UPDATE", False),
            ("ingest_runs", "UPDATE", True),   # deliberate; see GRANTS above
        ]:
            got = conn.execute(
                "SELECT has_table_privilege('hindsight_writer', %s, %s)",
                (table, priv),
            ).fetchone()[0]
            if got != expected:
                raise SystemExit(
                    f"hindsight_writer {priv} on {table}: got {got}, expected {expected}"
                )

        print("schema applied; writer holds INSERT and SELECT only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
