# Methods

Failures and limitations first, because a methods document that opens with the
procedure and buries the exclusions is an advertisement.

---

## Known limitations, stated before any result

1. **First publication is approximated by `realtime_start`.** ALFRED records the
   date a value entered the archive, which is the release date for the series it
   covers but is not guaranteed to be the moment a human could have acted. Any
   decision taken intraday on release day is outside what this method can see.

2. **Vintage granularity is daily.** Two revisions on the same day are one row.
   For monthly macro series this has no effect; for the GB settlement extension
   it does, and the run label is carried explicitly for that reason.

3. **The GB extension cannot be validated the way the US series can.** No public
   vintage archive exists for it. That is why it is an extension: the method is
   marked where marking is possible, then applied where it is not. Any GB result
   inherits the uncertainty of an unmarked method and is labelled as such.

4. **`RSAFS` is a control, not a placebo.** It is expected to revise little at
   these horizons. If it revises as much as `PAYEMS`, the most likely explanation
   is a bug in us, and that is the reading that will be published.

5. **The pandemic period is excluded from the primary window** and reported
   separately. Pooling it would let one episode carry the headline. This was
   fixed in `PREREGISTRATION.md`, not chosen after seeing the counts.

6. **A flip is not a mistake.** It is a decision that would have gone differently
   on different evidence. Nothing here establishes which evidence was better.

---

## Procedure

### Ingest

`series/observations` with `output_type=1` returns one row per distinct value a
reference period has held, with the interval it held it. `realtime_start` becomes
`vintage_date`; the row is appended. Re-running appends nothing, because
`(series_id, ref_period_start, vintage_date)` is the primary key and a repeat
insert raises rather than replacing.

Values published as missing arrive as `"."` and are stored `NULL`. A period we
failed to collect is absent entirely. These are different states and are never
collapsed: one is the publisher saying nothing, the other is us not looking.

### Reconstructing a vintage

A value is visible on date *v* iff `realtime_start <= v <= realtime_end`. This is
the only place the archive is collapsed to a single view, and it is the function
Gate 1 marks against ALFRED's own vintage endpoint.

### The rule

Three-month moving average of the unemployment rate, minus the minimum of that
moving average over the preceding twelve months; fires at `>= 0.50`.

Windows are required to be contiguous. A window overlapping a gap yields "not
computable", never an average over fewer months than the rule specifies.
Shortening the window silently is how a hole in collection becomes a firing that
never happened.

Arithmetic is exact decimal. See the README for why this changed an answer.

The gap is then rounded to two decimal places, half-up, before it is compared to
the threshold (Amendment 1). The rule fires on the number an analyst would read
off the published series, not on a value carrying repeating digits that a rate
published to one decimal place cannot support. `SahmPoint.gap_exact` retains the
unrounded value so the rounding can be inspected rather than taken on trust.

This is not a tolerance. It is part of the rule's definition, and it decides
boundary months: a gap of 0.4972 does not fire, and one of 0.4951 does.

### The comparison

For reference month *m*:

- `fire_rt(m)` — the rule evaluated on the vintage current on the day *m* was
  first published.
- `fire_now(m)` — the rule evaluated on the vintage current on the freeze date.

`fire_rt` is **not** today's series truncated at *m*. A truncated modern series
still carries every later correction to earlier months, and those corrections
feed the twelve-month minimum the rule subtracts. That distinction is the entire
project, and `tests/test_replay.py::test_flip_never_computed_from_truncated_modern_series`
exists to fail if it is ever lost.

Months not computable in either view are counted against coverage and never
silently counted as agreement.

---

## Gate 2, first run: FAILED

Recorded here in full because a gate that fails and is then quietly redefined is
worse than no gate. **2026-08-26, freeze date 2026-09-01.**

| | |
|---|---|
| Gate 1, `capture_faithful` | **PASS** — 0 of 111,948 month-vintage comparisons failed, worst \|diff\| 0.0 |
| Gate 2, `rule_reproduces` | **FAIL** — 3 of 528 months disagree with `SAHMREALTIME`, worst \|diff\| 0.20 |

The three: **1976-12, 1977-12, 1981-12.** All December. None elsewhere.

### What was found

For each of the three, `scripts/find_vintage.py` searched every vintage `UNRATE`
has ever had and asked which one reproduces FRED's published figure exactly:

| Month | Our release-day gap | `SAHMREALTIME` | Earliest vintage reproducing theirs |
|---|---|---|---|
| 1976-12 | 0.53 | 0.47 | 1977-02-04 — 23 days after release, 1 vintage later |
| 1977-12 | −0.17 | −0.13 | 1978-02-03 — 23 days after release, 1 vintage later |
| 1981-12 | 1.27 | 1.07 | 1982-02-05 — 28 days after release, 1 vintage later |
| **1980-12** *(control, agrees)* | 1.57 | 1.57 | 1981-01-09 — **release day, 0 vintages later** |

At the February release following each failing December, BLS restates a
multi-year span of seasonally adjusted history — 10, 38 and 57 months
respectively, reaching back as far as 1970. That is the annual seasonal
adjustment revision. At the next release following the control December, **zero**
months were restated, and the control agrees.

**`SAHMREALTIME`'s December values reflect the annual revision that lands the
month after December is published.** A strict release-day reading cannot, because
on that day the revision does not exist yet.

### What was deliberately not done

- The tolerance was **not** widened. Amendment 1 closed that door in advance,
  before this failure was visible, which is the only reason the door stayed shut.
- Our definition was **not** changed to match the benchmark. Adjusting the method
  until the benchmark agrees is not validation, and it would have been trivially
  easy here — one vintage's difference.
- The result was **not** reported as a pass with a footnote.

Both readings are recorded because the disagreement is evidence about the
benchmark as much as about us, and which of the two is "correct" is a
methodological choice, not a fact.

### Gate 2b, same run: ALSO FAILED

Amendment 2 added Gate 2b — the same comparison under the benchmark's apparent
convention, the vintage one release later, applied uniformly to every month
rather than carved out for December. It failed worse.

| Gate | Convention | Result | Failing months |
|---|---|---|---|
| Gate 2 | vintage on release day | 3 / 528 fail | **3 Decembers**, and nothing else |
| Gate 2b *(post-hoc)* | vintage one release later | 25 / 528 fail | **25 Novembers**, and nothing else |

The two failure sets are **disjoint and calendar-locked**. Release-day
reproduces every November and misses three Decembers; one-release-later
reproduces every December and misses twenty-five Novembers. Neither convention
is wrong sometimes and right other times in the way an implementation error
would be — each is exactly right for one calendar month and exactly wrong for
the other.

### The conclusion, which is not the one that was wanted

**`SAHMREALTIME` cannot be reproduced from `UNRATE` vintages by any single
uniform vintage convention.** Its construction mixes conventions across calendar
months, and that mixing is not described in its own metadata.

This is stated as a limitation of the *validation*, not as an accusation. The
benchmark may well be built from a monthly snapshot process whose timing relative
to the annual seasonal revision simply varies — the revision itself landed in
February in some years of this sample and in January in others, which is enough
to produce exactly this pattern.

### Consequence, applied as written

`PREREGISTRATION.md` says, in the section fixed before any data was downloaded:

> If Gate 2 fails, the failure is published and the GB extension does not run.

Gate 2 failed. Therefore, as of this run:

- **The primary outcome is not computed.** `scripts/outcome.py` refuses, and the
  refusal is enforced by reading `gates.json` rather than by intention.
- **The GB settlement extension does not run.**
- **No third gate was written.** Two attempts at a convention that would let the
  benchmark agree with us is already the edge of acceptable; a third, chosen
  after seeing which months failed, would be gate-shopping with extra steps. The
  possibility was named in Amendment 2 before this result existed: *"If Gate 2b
  fails as well, the reading is that something else is wrong and neither
  convention explains it."* That is the reading.

What remains available is **diagnosis**, which changes no threshold and gates
nothing: characterising when the annual revision landed in each year, and whether
that timing accounts for the November/December split.

### The diagnosis, run: the split is the BLS release calendar

**2026-08-30.** `scripts/diagnose_revision_calendar.py`. This is the diagnosis
named above. It changes no threshold, defines no convention, and no gate verdict
moves. `artifacts/revision_calendar.json` holds the full table.

For each reference year the script finds the January–March release carrying the
largest restatement of previously published history — the annual seasonal
adjustment revision — and records the calendar month it landed in. The
prediction was written into the script's docstring before the numbers were
printed, and it follows from the release arithmetic alone:

> November *Y* is released in early December *Y*, so Gate 2b reads the January
> *Y+1* release for it. December *Y* is released in early January *Y+1*, so Gate
> 2 reads that release and Gate 2b reads February *Y+1*. If the benchmark
> reflects the annual revision, then a **January** landing should break Gate 2b's
> November and leave Gate 2's December alone, and a **February** landing should
> do the reverse.

| | |
|---|---|
| Gate 2 December failures with a **February** landing | **3 of 3** |
| Gate 2b November failures with a **January** landing | **25 of 25** |
| Failures left unexplained by the landing month | **0** |

| Landing month | Gate 2 Dec | Gate 2b Nov | Years |
|---|---|---|---|
| January | ok | ok | 14 |
| January | ok | **FAIL** | 25 |
| February | **FAIL** | ok | 3 |
| February | ok | ok | 1 |
| March | ok | ok | 1 |

The correspondence is tighter than the prediction required. The prediction was
one-directional — a revision that moves no gap past the tolerance cannot cause a
failure, so quiet years prove nothing either way. In fact the match is exact in
both directions: **in all 44 years, the annual revision moved the November gap
if and only if Gate 2b failed that November, and moved the December gap if and
only if Gate 2 failed that December.** Every one of the 16 quiet years has a
revision that landed and moved neither gap by more than 0.005.

The three February landings are 1977-02-04, 1978-02-03 and 1982-02-05 — the same
three already recorded above, found there by searching one month at a time and
confirmed here by a procedure that looked at all 44 years without knowing which
three mattered. One landing falls outside both: 1996-03-08, restating 44 months
back to 1990-01.

**What this establishes.** The disagreement between our reconstruction and
`SAHMREALTIME` is not scattered, is not an implementation error, and is not
unexplained. It is the BLS annual seasonal-adjustment release calendar, which
moved between January and February across the sample. `SAHMREALTIME`'s November
values track the release-day vintage; its December values track the vintage that
carries that year's annual revision, whenever that arrives.

**What this does not establish.** It is an inference from the public vintage
record, not a description confirmed by the publisher. It says the mixing is
systematic and identifies what it tracks; it does not show that FRED constructs
the series that way, and nothing here says the series is wrong.

**What this does not change.** Gate 2 still failed, and the preregistration binds
on the verdict, not on how well the failure is now understood. The primary
outcome is still not computed and the GB extension still does not run. Producing
an explanation for a failed gate and then treating the explanation as a pass is
the exact move the gate exists to prevent, and it is more tempting now than it
was before the explanation existed. Of the three routes out listed in
`DECISION_MEMO.md`, this advances the second — the discrepancy is now
characterised rather than unexplained — without completing it.

---

## What Gate 1 did and did not test

**Recorded 2026-08-30, after the fact.** The preregistration describes Gate 1 as
testing "our storage and our joins". In the run recorded in `artifacts/gates.json`
it tested the joins and not the storage: `scripts/run_gates.py` pulled intervals
straight from the ALFRED API, because no code existed to read them back out of
the store. The gate's arithmetic was exercised end to end; its premise was not.

That is a smaller gap than it sounds, and it is stated rather than quietly
closed because the verdict looks identical either way — which is precisely the
property that lets such a gap survive.

Two things now hold:

1. `src/hindsight/store.py` reconstructs real-time intervals from the
   append-only rows, deriving each interval's end from the next row rather than
   storing it. `scripts/run_gates.py --source store` uses it, and `auto` prefers
   it whenever a DSN is configured.
2. `gates.json` records `intervals_from`, so no reader has to take the source of
   a gate run on trust.

The derivation was checked against the live archive on 2026-08-30: across 1,254
consecutive pairs of `UNRATE` vintages, `realtime_end` was the day before the
next `realtime_start` without exception, and every currently-published value
carried the archive's open-ended sentinel. All 2,197 live intervals survive the
round trip through the store's columns unchanged, so the representation loses
nothing. `tests/test_store_roundtrip.py` holds that offline, and
`scripts/smoke.py` re-checks it against the live archive.

**The store path has not been run.** There is no Postgres on the machine these
notes were written on, so `--source store` is exercised by CI and by the offline
round-trip test, and nowhere else yet. Until a gate run records
`"intervals_from": "store"`, the storage half of Gate 1's premise remains
untested, and the recorded run says so in its own artifact.

## What the version history does not establish

**Recorded 2026-08-30, at the first commit.** `PREREGISTRATION.md` opens by
saying it was "committed before any vintage was downloaded". Until today this
repository had **no commits at all**: the working tree existed, the git history
did not. Every file here — the preregistration, the code, the gate results and
the diagnosis — enters version control in a single commit, dated after the gates
had already run.

So the history proves nothing about the ordering, and it is worth being exact
about what that costs and what it does not:

- **The claim is not withdrawn.** The preregistration was written before the
  gates ran; that is a fact about how the work happened.
- **It is no longer independently checkable.** A reader who wants evidence
  rather than assurance does not have it here, and would have had it from a
  commit made on 2026-08-26.
- **This is the failure mode the project is about.** A record that is created
  after the fact is indistinguishable, from the outside, from one that was kept
  all along — which is the whole argument of the README, applied to itself.

It is one commit rather than a sequence reconstructing how the work arrived,
because a reconstructed sequence would look like history and would not be any.
The files changed on 2026-08-30 were edited in place, and the state they held
before that day was not preserved anywhere; staging them as an earlier commit
would have dated a snapshot that never existed. The single commit is the honest
shape of what is actually known.

Nothing about the preregistration's *content* depends on this: the constants are
asserted against `src/hindsight/prereg.py` by `tests/test_preregistration.py`, so
a threshold cannot be edited to match a result without the build failing. That
enforcement is checkable from here on. The ordering claim is not.

`artifacts/` is tracked from this commit, having previously been gitignored. The
gate results are the record the preregistration binds on — `scripts/outcome.py`
reads `gates.json` to decide whether a finding is permitted at all — and a
repository that cannot show them cannot show the verdict it claims to obey.

## Exploratory

Anything in this section was run after the primary outcome and is not evidence
for it. It does not appear in `DECISION_MEMO.md`.

*(none yet)*

---

## Changelog

| Date | Change |
|---|---|
| 2026-08-26 | M0. Preregistration committed; schema, rule, replay and gates implemented against synthetic archives. No live vintage downloaded. |
| 2026-08-26 | Arithmetic changed from binary float to exact decimal after two months with an identical hand-computed gap of 0.50 returned different answers. `prereg.ARITHMETIC` and `prereg.BOUNDARY_INCLUSIVE` added to the preregistration before any live data existed. |
| 2026-08-26 | `as_of` was reading a value column whose name it had guessed from the documentation. The guess was wrong and the failure was silent — an empty vintage, which reconstructs as "nothing was published that day" and reads as a gap in collection. The column is now discovered, and an empty response raises. Caught by `scripts/smoke.py` before any ingest, which is why that script exists. |
| 2026-08-26 | Amendment 1: gap rounded to two decimal places, half-up, before meeting the threshold. Written and committed before Gate 2 was run for the first time. |
| 2026-08-30 | `tests/test_validation_gates.py` written. `PREREGISTRATION.md` had cited it since M0 as what enforces "both gates must pass before the primary outcome is computed at all", and it did not exist. A document naming an enforcement that was never written reads exactly like one that was. `tests/test_preregistration.py::test_every_test_file_the_document_cites_exists` now fails on any such citation. |
| 2026-08-30 | Gate 1's premise recorded honestly: the run in `gates.json` read intervals from the API, not the store, so it tested the joins and not the storage. `src/hindsight/store.py` reads the archive back out of the append-only rows, `run_gates.py` records `intervals_from`, and the round trip is checked offline and against the live archive. See *What Gate 1 did and did not test*. |
| 2026-08-30 | Diagnosis run: the Gate 2 / Gate 2b failure split is the BLS annual seasonal-adjustment release calendar, 3/3 and 25/25 with no unexplained failure. Changes no verdict; the primary outcome remains uncomputed. |
| 2026-08-30 | Gates re-run against a freshly downloaded archive, four days after the first run. Every verdict, every failing month and every difference reproduced exactly: Gate 1 0/111,948, Gate 2 3/528, Gate 2b 25/528, worst \|diff\| unchanged. `intervals_from` is `alfred-api` in this run, for the reason recorded above. |
| 2026-08-30 | Every script forced its output stream to UTF-8. On a Windows console `scripts/smoke.py` crashed part-way through on an em dash, turning a diagnostic that had passed five checks into a traceback with no verdict. A check that cannot print is a check that did not run. |
