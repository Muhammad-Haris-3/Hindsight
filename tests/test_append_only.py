"""Append-only is a database grant, not a code convention.

A test suite that never attempts the forbidden write proves nothing about
whether the write is forbidden. These tests connect as the writer role CI
actually uses and assert that restating the past raises.

They skip without HINDSIGHT_WRITER_DSN, and the CI job that runs migrations
fails if they skip there -- see .github/workflows/gates.yml.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest

psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("HINDSIGHT_WRITER_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="HINDSIGHT_WRITER_DSN unset")


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        yield c
        # psycopg commits when this block exits cleanly. Nothing these tests
        # write may ever reach the store the gates read, so the last word is a
        # rollback rather than whatever the test happened to leave open.
        c.rollback()


@pytest.fixture
def run_id(conn):
    """A series row and an ingest run, inside the test's own transaction.

    `observations.ingest_run_id` is NOT NULL and references `ingest_runs`, and
    `series_id` references `series`. Both tables are empty when this job runs,
    because the append-only tests deliberately run *before* the first ingest --
    so a test that does not create its own rows never reaches the constraint it
    came to check.

    That is not hypothetical. Until 2026-08-30 the backdating test took its
    `ingest_run_id` from `(SELECT run_id FROM ingest_runs LIMIT 1)`, which was
    NULL on an empty table, and the insert died on NOT NULL before Postgres ever
    evaluated the `vintage_after_period` CHECK. The test failed, and the
    constraint it exists to exercise had never once been exercised. See
    METHODS.md.

    Everything seeded here is rolled back; none of it is committed.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO series (series_id, source, title, units, frequency, role)"
            " VALUES ('UNRATE','alfred','UNRATE','','M','primary')"
            " ON CONFLICT DO NOTHING"
        )
        cur.execute("INSERT INTO ingest_runs (source) VALUES ('test') RETURNING run_id")
        value = cur.fetchone()[0]
    yield value
    conn.rollback()


def test_writer_cannot_update_observations(conn):
    with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("UPDATE observations SET value = value + 1")
    conn.rollback()


def test_writer_cannot_delete_observations(conn):
    with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM observations")
    conn.rollback()


def test_writer_cannot_truncate_observations(conn):
    with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("TRUNCATE observations")
    conn.rollback()


INSERT = (
    "INSERT INTO observations (series_id, ref_period_start, ref_period_end,"
    " vintage_date, value, ingest_run_id) VALUES ('UNRATE',%s,%s,%s,4.0,%s)"
)

JANUARY = (dt.date(2020, 1, 1), dt.date(2020, 1, 31))


def test_a_period_cannot_be_described_before_it_begins(conn, run_id):
    """The CHECK constraint that makes backdating the cheapest fake unavailable.

    Dating a real-time result before the evidence could possibly exist is the
    cheapest way to fake one, and this is what makes it unavailable.
    """
    with conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(INSERT, (*JANUARY, dt.date(2019, 12, 15), run_id))
    conn.rollback()


@pytest.mark.parametrize(
    "vintage,why",
    [
        (dt.date(2020, 2, 7), "the ordinary case: published after the month ended"),
        (dt.date(2020, 1, 29), "published inside its own reference month"),
        (dt.date(2020, 1, 1), "published on the first day of the period"),
    ],
)
def test_rows_the_check_must_admit(conn, run_id, vintage, why):
    """The positive controls, without which the test above proves nothing.

    A row rejected for some unrelated reason -- a missing foreign key, a null
    column -- looks exactly like a row the CHECK caught, and for months one did.
    Only a passing insert makes the rejection above attributable.

    The middle case is not hypothetical and is the reason the constraint was
    relaxed on 2026-08-30: on 1961-08-29 the BLS published August 1961's
    unemployment rate and payroll count while August was still running, because
    the household survey references the week containing the 12th rather than the
    whole month. The stricter constraint rejected both rows and stopped the
    entire ingest. See db/schema.sql and METHODS.md.
    """
    with conn.cursor() as cur:
        cur.execute(INSERT, (*JANUARY, vintage, run_id))
    conn.rollback()


def test_the_same_vintage_cannot_be_appended_twice(conn, run_id):
    """Idempotent ingest: a re-run appends nothing rather than duplicating.

    Self-sufficient on purpose. This used to read a row back from `observations`
    and skip when the table was empty -- which is its state whenever these tests
    run before an ingest, so in CI it skipped rather than tested.
    """
    with conn.cursor() as cur:
        cur.execute(INSERT, (*JANUARY, dt.date(2020, 2, 7), run_id))

    with conn.cursor() as cur, pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(INSERT, (*JANUARY, dt.date(2020, 2, 7), run_id))
    conn.rollback()
