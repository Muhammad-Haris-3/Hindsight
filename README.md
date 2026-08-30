# Hindsight

**The record changes after you have read it.**

Statistical agencies and grid operators revise published figures — sometimes for
months, sometimes for years. Every backtest you have ever seen is computed
against the numbers *as they stand today*. Every decision it claims to evaluate
was made against the numbers *as they stood then*. Those are different datasets,
and for most series nobody keeps a public record of the gap.

Hindsight stores every vintage of a handful of series, replays a decision rule
people actually use against what was knowable on the day, and counts the
decisions that flip.

> **Status: gates run against live data. The primary outcome is not computed,
> and there is a finding anyway — about the benchmark.**
>
> Gate 1 passed. **Gate 2 failed**: our real-time replay disagrees with
> `SAHMREALTIME`, FRED's own real-time version of the same rule, on 3 of 528
> months. A post-hoc second convention (Gate 2b) fixed those three and broke 25
> different ones. The failure pattern turns out to be fully accounted for by the
> BLS annual seasonal-revision calendar — 28 of 28 failures, no leftovers — which
> explains the disagreement without repairing it.
>
> The preregistration says a failed Gate 2 is published and the extension does
> not run. Both hold: the flip count is **not** computed and the GB extension has
> **not** been run. [`DECISION_MEMO.md`](DECISION_MEMO.md) is the finding in plain
> English. [`PREREGISTRATION.md`](PREREGISTRATION.md) fixed the window, the
> threshold, the series list and both gates in advance.

---

## The build is red on purpose

[![gates](https://github.com/Muhammad-Haris-3/Hindsight/actions/workflows/gates.yml/badge.svg)](https://github.com/Muhammad-Haris-3/Hindsight/actions/workflows/gates.yml)

**A green badge here would be the bug.** `scripts/run_gates.py` returns the gate
verdict as its exit status, so a failed gate fails the job. Gate 2 fails.
Therefore the job is red, and stays red until the validation problem is resolved
rather than tuned away.

The last run, in full:

```
tests                            62 passed, 1 skipped
append-only (against Postgres)   8 passed
ingest                           65,057 rows across 3,619 vintages
run gates                        2,197 intervals for UNRATE (from store)
  [PASS] capture_faithful        0/111,948 failed, worst |diff| 0.0
  [FAIL] rule_reproduces         3/528 failed, worst |diff| 0.20
  [FAIL] rule_reproduces_offset  25/528 failed, worst |diff| 0.10
intervals_from: store
```

Every step succeeds except the gate itself. The pipeline is working; it is
reporting a real negative result, which is the thing it was built to be able to
do. A build that went green here would mean a finding had been computed after
its own validation failed — the one outcome `PREREGISTRATION.md` exists to make
impossible.

The three failing months, and why they fail, are in
[`DECISION_MEMO.md`](DECISION_MEMO.md).

---

## The problem, in one example

An indicator says a recession began in month *M*. It says so because the
unemployment rate three months earlier sat at a particular low, and the rule
measures today's average against that low.

Two years later the agency restates that earlier month — routine, small, correct.
The low is now slightly higher. The gap is now slightly smaller.

**Re-run the indicator today and it never fired.**

Nobody edited the decision. Nobody edited the indicator. The decision was made on
evidence that no longer exists, and every subsequent evaluation of it — every
"was the indicator right?" — silently uses evidence that was not available when
it mattered. The measurement changed after the decision it describes.

This is a solved problem in principle. It has a name: point-in-time correctness.
Essentially nobody applies it outside finance.

## Why it can be checked rather than argued

The tempting version of this project asserts that revisions matter and asks to be
believed. This one does not have to.

**For US macro series, the truth is already on the table.** ALFRED holds every
vintage back decades, and FRED publishes `SAHMREALTIME` — its own real-time
version of the rule. So the method can be *marked*: reconstruct the archive from
scratch, replay the rule from first-publication vintages, and check the answer
against one somebody else published.

Only after it reproduces a known answer is it pointed at GB settlement data,
where no equivalent archive exists and nobody can mark it.

**The deliverable is not "revisions are big." It is the error of this method
against cases where the answer was already known** — and the threshold it has to
clear was written down first.

## How the record stays honest

| Mechanism | What it prevents |
|---|---|
| **A restatement is a new row.** The schema has no column to overwrite; `(series, period, vintage)` is the primary key | A store where "we kept the old value" is a promise made by careful code |
| **The writer role holds `INSERT` and nothing else** — by `REVOKE`, not convention. `tests/test_append_only.py` connects as that role and asserts `UPDATE` raises | An append-only claim nobody ever tried to violate |
| **`CHECK (vintage_date >= ref_period_start)`** | Backdating — dating a real-time result before the evidence could exist. It read `>= ref_period_end` until the archive proved that wrong: BLS published August 1961 two days before August ended |
| **Gates before findings.** Both validation gates must pass before the primary outcome is computed at all | A robustness check run afterwards, on a result someone already likes |
| **A fixed random seed for the Gate 1 sample** | Redrawing the sample until it passes |
| **Constants asserted against the preregistration by the test suite** | A document that states one threshold while the code uses another |
| **Exact decimal arithmetic** | A finding about revisions that is partly a finding about IEEE 754 (see below) |
| **Coverage published beside every flip count** | A gap in collection reading as a period in which nothing was revised |

### One check worth singling out

The rule fires at a gap of **exactly 0.50**, and the unemployment rate is
published to one decimal place, so real prints land exactly on the threshold.

Under binary floats, `4.4 - 3.9` is `0.5000000000000004` or `0.4999999999999996`
depending on summation order. During development two months with an identical
hand-computed gap of 0.50 returned different answers, and the disagreement was
invisible at every print precision a person would normally use.

Arithmetic is exact decimal throughout, and the boundary convention is fixed in
the preregistration rather than settled later by whichever choice produced a more
interesting count.

## What this project will not do

- **It will not build a model.** No estimator, no forecast, no fitted parameter.
  Thirteen projects preceded this one and most of them contained a model; the
  subject here is the data.
- **It will not claim a revision was wrong.** A revision is the publisher doing
  its job. The finding concerns decisions taken before it arrived.
- **It will not report a flip count without the coverage it was computed over.**

## Architecture

```
ALFRED (api key, free)  ·  Elexon Insights (keyless)
        |
        v
GitHub Actions — ingest, gates, seal        idempotent · run-logged
        |
        v
observations   append-only; (series, period, vintage) is the key
        |
        +--> gates ──► gate_results   both must pass before any finding
        |
        v
   replay ──► flips ──► static snapshots
        |
        v
FastAPI (read-only) ──► Next.js
```

Serving reads snapshots published by the pipeline, not the database. This is
carried over from GridCast, where a free-tier data-transfer allowance was spent
by page views and took the whole site down.

## Layout

| Path | |
|---|---|
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | Fixed before any vintage was downloaded. Enforced by `tests/test_preregistration.py` |
| [`METHODS.md`](METHODS.md) | Every procedure, and every exclusion with the direction of its bias |
| [`DECISION_MEMO.md`](DECISION_MEMO.md) | The finding, in plain English |
| `db/schema.sql` | The append-only store, and the grants that enforce it |
| `src/hindsight/rules/sahm.py` | The rule. Ignorant of vintages by design |
| `src/hindsight/replay.py` | The one comparison the project exists to make |
| `src/hindsight/gates.py` | The two gates that must pass first |
| `src/hindsight/store.py` | Reading the archive back out of the append-only rows |
| `tests/test_validation_gates.py` | The gates fail when they should, and no finding may outrun them |
| `scripts/diagnose_revision_calendar.py` | Why the gates failed. Diagnosis; gates nothing |

## Running

```bash
python -m pip install -e ".[dev]"
```

```bash
python -m pytest
```

The suite runs offline; tests needing a live key or database skip rather than
fail. Set `HINDSIGHT_FRED_API_KEY` ([free](https://fredaccount.stlouisfed.org/apikeys))
and `HINDSIGHT_WRITER_DSN` to run the rest.
