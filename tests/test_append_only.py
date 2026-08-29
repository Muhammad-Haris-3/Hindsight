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


def test_a_period_cannot_be_described_before_it_ends(conn):
    """The CHECK constraint that makes backdating the cheapest fake unavailable."""
    with conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO observations
                (series_id, ref_period_start, ref_period_end, vintage_date,
                 value, ingest_run_id)
            VALUES ('UNRATE', %s, %s, %s, 4.0,
                    (SELECT run_id FROM ingest_runs ORDER BY run_id LIMIT 1))
            """,
            (dt.date(2020, 1, 1), dt.date(2020, 1, 31), dt.date(2020, 1, 15)),
        )
    conn.rollback()


def test_the_same_vintage_cannot_be_appended_twice(conn):
    """Idempotent ingest: a re-run appends nothing rather than duplicating."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT series_id, ref_period_start, ref_period_end, vintage_date, value,"
            " ingest_run_id FROM observations LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        pytest.skip("no observations ingested yet")

    with conn.cursor() as cur, pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO observations (series_id, ref_period_start, ref_period_end,"
            " vintage_date, value, ingest_run_id) VALUES (%s,%s,%s,%s,%s,%s)",
            row,
        )
    conn.rollback()
