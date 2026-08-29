-- Hindsight schema.
--
-- The thesis of this project is that a published figure is not a fact but an
-- observation with a date attached. The schema is required to make the opposite
-- claim inexpressible: there is no column to overwrite, so "the number was
-- always this" cannot be recorded even by mistake.

BEGIN;

CREATE TABLE IF NOT EXISTS series (
    series_id        text PRIMARY KEY,
    source           text        NOT NULL,          -- 'alfred' | 'elexon'
    title            text        NOT NULL,
    units            text        NOT NULL,
    frequency        text        NOT NULL,          -- 'M' | 'Q' | 'HH'
    role             text        NOT NULL,          -- 'primary' | 'secondary' | 'control' | 'extension'
    prereg_locked    boolean     NOT NULL DEFAULT true,
    first_seen_at    timestamptz NOT NULL DEFAULT now()
);

-- Coverage is evidence. A gap in collection must not read as a period in which
-- nothing was revised.
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id           bigserial PRIMARY KEY,
    source           text        NOT NULL,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    status           text        NOT NULL DEFAULT 'running',  -- running|ok|failed
    rows_appended    integer     NOT NULL DEFAULT 0,
    vintages_seen    integer     NOT NULL DEFAULT 0,
    detail           jsonb       NOT NULL DEFAULT '{}'::jsonb
);

-- One row per (what period, when it was said). A restatement of an old period
-- is a NEW ROW. There is deliberately no `value` update path.
CREATE TABLE IF NOT EXISTS observations (
    series_id        text        NOT NULL REFERENCES series(series_id),
    ref_period_start date        NOT NULL,
    ref_period_end   date        NOT NULL,
    vintage_date     date        NOT NULL,          -- the day the publisher said it
    value            numeric,                       -- NULL = published as missing
    run_label        text,                          -- Elexon settlement run: II/SF/R1/R2/R3/RF
    ingested_at      timestamptz NOT NULL DEFAULT now(),
    ingest_run_id    bigint      NOT NULL REFERENCES ingest_runs(run_id),

    PRIMARY KEY (series_id, ref_period_start, vintage_date),

    -- A period cannot be described before it has ended.
    CONSTRAINT vintage_after_period CHECK (vintage_date >= ref_period_end),
    CONSTRAINT period_ordered       CHECK (ref_period_end >= ref_period_start)
);

CREATE INDEX IF NOT EXISTS obs_series_period ON observations (series_id, ref_period_start);
CREATE INDEX IF NOT EXISTS obs_series_vintage ON observations (series_id, vintage_date);


-- Results of the two preregistered gates. Recorded, not asserted in prose.
CREATE TABLE IF NOT EXISTS gate_results (
    gate             text        NOT NULL,          -- 'capture_faithful' | 'rule_reproduces'
    checked_at       timestamptz NOT NULL DEFAULT now(),
    passed           boolean     NOT NULL,
    n_checked        integer     NOT NULL,
    n_failed         integer     NOT NULL,
    max_abs_diff     numeric,
    detail           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (gate, checked_at)
);

COMMIT;

-- ---------------------------------------------------------------------------
-- Append-only, enforced by grant rather than by convention.
-- Run as owner, once, after the tables exist. The writer role used by CI holds
-- INSERT and nothing else on observations; it physically cannot restate the
-- past. The reader role used by the API holds SELECT and nothing else.
-- ---------------------------------------------------------------------------
--
--   REVOKE ALL ON observations FROM hindsight_writer;
--   GRANT  INSERT, SELECT ON observations TO hindsight_writer;
--   REVOKE UPDATE, DELETE, TRUNCATE ON observations FROM hindsight_writer;
--
--   GRANT  SELECT ON ALL TABLES IN SCHEMA public TO hindsight_reader;
--   REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM hindsight_reader;
--
-- tests/test_append_only.py connects as hindsight_writer and asserts that an
-- UPDATE and a DELETE both raise InsufficientPrivilege. A passing test suite
-- that never attempts the forbidden write proves nothing.
