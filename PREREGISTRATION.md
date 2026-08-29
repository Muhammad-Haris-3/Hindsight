# Preregistration

**Committed before any vintage was downloaded, any rule was replayed, and any
disagreement was counted.** Every constant in this document appears in
`src/hindsight/prereg.py` and is asserted against this file by
`tests/test_preregistration.py`. Changing a number here without changing it
there fails the build, and vice versa.

Amendments are appended below the line marked *Amendments*, with a date and a
reason. Nothing above that line is ever edited.

---

## H0 — What is being claimed

**The claim is not that revisions are large.** The claim is that a decision rule
replayed on today's data and the same rule replayed on the data that existed at
the time do not always give the same answer, and that the size of that
disagreement has never been published for the series studied here.

If the disagreement turns out to be zero, that is the finding and it will be
published with the same prominence as any other.

## H1 — Primary quantity

For a rule `R` and a series `S`:

- **`fire_rt(m)`** — did `R` fire for reference month `m`, computed from the
  vintage of `S` that existed on the day `m` was first published?
- **`fire_now(m)`** — does `R` fire for reference month `m`, computed from the
  vintage of `S` current on the freeze date (below)?

**Primary outcome: the flip count** — `#{ m : fire_rt(m) != fire_now(m) }` over
the study window — and **the flip rate**, that count divided by the number of
reference months in the window.

A secondary outcome is the **timing displacement**: for each contiguous run of
firings, the signed difference in months between the first `fire_rt` month and
the first `fire_now` month.

## Fixed before the fact

| Constant | Value | Where |
|---|---|---|
| Study window (reference months) | `1976-01` .. `2019-12` | `prereg.WINDOW_START`, `prereg.WINDOW_END` |
| Freeze date for "now" | `2026-09-01` | `prereg.FREEZE_DATE` |
| Sahm threshold | `0.50` pp | `prereg.SAHM_THRESHOLD` |
| Arithmetic | `decimal-exact` | `prereg.ARITHMETIC` |
| Gap of exactly 0.50 fires | `True` | `prereg.BOUNDARY_INCLUSIVE` |
| Sahm short window | `3` months | `prereg.SAHM_SHORT_WINDOW` |
| Sahm lookback | `12` months | `prereg.SAHM_LOOKBACK` |
| Material revision | any revision that changes `fire_*` for any month | `prereg.MATERIAL_IS_DECISION_FLIP` |
| Reconstruction tolerance | `0.005` pp, all months | `prereg.RECONSTRUCTION_TOL` |
| Minimum vintage coverage to publish | `0.95` of months in window | `prereg.MIN_VINTAGE_COVERAGE` |

Arithmetic is exact decimal rather than binary float, and a gap of exactly
0.50 counts as firing. Both were fixed here because the boundary is not
hypothetical: the rate is published to one decimal place and the threshold is
reached exactly. Under floats, two months with the same gap can disagree
depending on summation order, which would put IEEE 754 inside the headline.

The window ends `2019-12` deliberately. The pandemic labour-market series is a
structural break that would dominate any revision statistic computed across it,
and including it would let a single episode carry the headline. The 2020-2025
period will be reported **separately and additionally**, never pooled.

## Series studied

Chosen now, in full, so that a series cannot be added later because it looked
promising and cannot be dropped later because it did not.

| Series | Source | Role |
|---|---|---|
| `UNRATE` | ALFRED | Primary. Input to the Sahm rule |
| `PAYEMS` | ALFRED | Secondary. Heavily revised by construction (benchmark + seasonal) |
| `GDPC1` | ALFRED | Secondary. Revised for years, not months |
| `INDPRO` | ALFRED | Secondary. Annual benchmark revisions |
| `RSAFS` | ALFRED | Control. Expected to revise little at the horizons studied |
| GB settlement volumes | Elexon Insights | Extension. No public vintage archive exists |

`RSAFS` is a control in the specific sense that a method which reports large
revisions everywhere, including here, is measuring its own bugs.

## Rules replayed

1. **Sahm rule.** Three-month moving average of `UNRATE`, minus the minimum of
   that moving average over the preceding twelve months; fires at `>= 0.50`.
2. **Carbon-cheapest-hour.** For each GB settlement day, the half-hour ranked
   lowest by carbon intensity. Replayed across settlement runs II -> SF -> R1 ->
   R2 -> R3 -> RF. Fires = the chosen half-hour.

No third rule will be added. If a third rule is later interesting it belongs to
a different study with its own preregistration.

## Validation before any finding is reported

Two gates. **Neither is a robustness check run afterwards; both must pass before
the primary outcome is computed at all**, and both are enforced by
`tests/test_validation_gates.py`.

**Gate 1 — the capture is faithful.** Reconstruct each series' full vintage
history from the ALFRED API into our own store, then re-derive, for a random
sample of 200 (series, reference month, vintage date) triples, the value ALFRED
reports directly. Every triple must agree within `RECONSTRUCTION_TOL`. This
tests our storage and our joins, not our arithmetic.

**Gate 2 — the rule is implemented correctly.** FRED publishes `SAHMREALTIME`,
its own real-time Sahm series. Our `fire_rt` reconstructed from `UNRATE`
vintages must reproduce `SAHMREALTIME` for every month in the window, within
`RECONSTRUCTION_TOL`.

Gate 2 is the point of the design. **The truth is already on the table for the
US series** — someone else has published the real-time answer — so our method
can be marked rather than trusted. Only after it reproduces a known answer is it
pointed at GB settlement data, where no equivalent archive exists and nobody can
mark it.

If Gate 2 fails, the failure is published and the GB extension does not run.

## Stopping rule

The primary outcome is computed **once**, on the full window, after both gates
pass. It is not recomputed with a different threshold, a different window, or a
different moving-average length. If any of those are explored they appear under
*Exploratory* in `METHODS.md`, labelled as such, and never in `DECISION_MEMO.md`.

## What would falsify the thesis

- Flip count of zero across all series and both rules.
- `RSAFS` revising as much as `PAYEMS` (indicates measurement error in us).
- Gate 1 failing on more than zero triples.

Any of these is a publishable result and will be published.

## What this project will not do

- **It will not build a model.** No estimator, no forecast, no fitted
  parameter. The subject is the data.
- **It will not claim a revision was wrong.** A revision is usually the
  publisher doing its job. The finding concerns decisions taken before it
  arrived, not the competence of the agency.
- **It will not recommend anyone stop using revised data.**

---

## Amendments

### Amendment 1 — 2026-08-26 — gap precision and the firing convention

**Made before Gate 2 was run for the first time. No gate result, and no flip
count, existed when this was written.**

`SAHMREALTIME`, the benchmark Gate 2 marks us against, is published to two
decimal places. Our gap is computed exactly, from a rate published to one
decimal place divided by three, so it carries repeating digits the benchmark
does not.

Comparing an exact value against a rounded one attributes the publisher's
rounding to our method. The maximum discrepancy from that source alone is 0.005
— exactly `RECONSTRUCTION_TOL` — so borderline months could fail Gate 2 while our
implementation was perfectly correct, and the obvious repair after seeing such a
failure would be to loosen the tolerance. That repair is unavailable now, which
is the point of writing this first.

Two things are therefore fixed:

| Constant | Value | Where |
|---|---|---|
| Gap precision | `2` decimal places | `prereg.GAP_PRECISION` |
| Rounding mode | `ROUND_HALF_UP` | `prereg.GAP_ROUNDING` |

1. **The gap is rounded to two decimal places before it is compared to the
   threshold**, half-up. The rule therefore fires on the gap as an analyst would
   read it off the published series, not on a value carrying digits the source
   never had. This is a decision about the *primary outcome*, not only about the
   gate: a gap of 0.4972 does not fire, and a gap of 0.4951 does.

2. **Gate 2 compares the rounded gap** to the benchmark, and
   `RECONSTRUCTION_TOL` stays at 0.005. It is not widened.

This continues the reasoning already recorded under `prereg.ARITHMETIC`: the
threshold is reached exactly by real prints, so every convention that decides a
boundary case is written down before it can be chosen to taste.

### Amendment 2 — 2026-08-26 — Gate 2b, designed after Gate 2 failed

**This amendment was written after seeing a gate fail. That makes every result
it produces weaker evidence than a preregistered one, and it is labelled as such
in `gates.json`, in `METHODS.md`, and in the code that computes it.**

Gate 2 failed: 3 of 528 months, all December, worst |diff| 0.20. The diagnosis is
recorded in full in `METHODS.md` — `SAHMREALTIME` reflects the annual seasonal
adjustment revision that arrives one release after December is published, and a
strict release-day reading cannot see it.

| Constant | Value | Where |
|---|---|---|
| Benchmark release offset | `1` | `prereg.GATE2B_RELEASE_OFFSET` |
| Marked post-hoc | `True` | `prereg.GATE2B_IS_POST_HOC` |

Three things are fixed by this amendment:

1. **Gate 2 is not repealed and its failure is not amended away.** It keeps its
   original definition, is re-run every time, and its failure remains the
   headline result of the validation section.
2. **Gate 2b applies the offset uniformly to every month**, never only to
   December. A rule reading "use the later vintage, but only where that helps" is
   not a convention, it is a fit, and it would pass by construction.
3. **`RECONSTRUCTION_TOL` is still not widened**, in either gate.

If Gate 2b passes for all months, the reading is: our implementation of the rule
is correct, and the two series differ by a documented vintage convention rather
than by an error. If Gate 2b fails as well, the reading is that something else is
wrong and neither convention explains it.

**The primary outcome continues to use the strict release-day definition**, not
the benchmark's. What was knowable on the day is the question the project asks;
adopting a convention that sees one release into the future in order to agree
with somebody else would answer a different one.

### Amendment 3 — 2026-08-30 — the Gate 2b reading, corrected by diagnosis

**Written after both gates had failed and after the diagnosis was run. It is
post-hoc, like Amendment 2, and it is weaker evidence than anything fixed in
advance. It changes no verdict, no threshold, no convention and no count.**
Nothing above the *Amendments* line is edited, and Amendment 2's text stands
exactly as written.

Amendment 2 fixed a reading in advance, before Gate 2b had run:

> If Gate 2b fails as well, the reading is that something else is wrong and
> neither convention explains it.

Gate 2b failed. That reading was applied on 2026-08-26 and recorded in
`METHODS.md` and `DECISION_MEMO.md`. **It is now superseded, and this amendment
exists so that the supersession is on the record rather than only in the
document that benefits from it.**

`scripts/diagnose_revision_calendar.py` characterises, for each of the 44
reference years in the window, which January–March release carried the largest
restatement of previously published history — the BLS annual seasonal-adjustment
revision — and which calendar month it landed in. The prediction was written into
that script before the years were counted, and follows from the release
arithmetic alone. It holds without exception:

| | |
|---|---|
| Gate 2 December failures in **February**-landing years | 3 of 3 |
| Gate 2b November failures in **January**-landing years | 25 of 25 |
| Failures unexplained by the landing month | 0 |

In all 44 years the annual revision moved the November gap if and only if Gate 2b
failed that November, and the December gap if and only if Gate 2 failed that
December. So the failures are explained — not by a third convention, but by the
release calendar of the revision itself, which moved between January and
February across the sample.

Three things are fixed by this amendment:

1. **The correction is to the reading, not to the verdict.** Gate 2 failed and
   that failure stands, unamended. The primary outcome is still not computed and
   the GB extension still does not run. Explaining a failure is not passing one,
   and the preregistration binds on the verdict.

2. **No third convention was written, and none may be.** The diagnosis is enough
   to say what `SAHMREALTIME`'s December values track, which is enough to build a
   Gate 2c that would pass. That is precisely why it is forbidden: a rule chosen
   after seeing which months it fixes is gate-shopping, ruled out in Amendment 2
   when no such rule was known. The prohibition is reaffirmed here, at the point
   where it first costs something.

3. **The characterisation is ours, not the publisher's.** It is an inference from
   the public vintage record. It shows the mixing is systematic and identifies
   what it tracks; it does not show that FRED constructs the series this way, and
   nothing in it says the series is wrong. Route 2 of `DECISION_MEMO.md` is
   therefore advanced and not closed — closing it means asking them.

This amendment fixes no new constant. It corrects a reading, and a reading is not
a parameter.
