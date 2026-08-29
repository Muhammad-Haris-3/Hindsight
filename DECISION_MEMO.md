# Decision memo

**Two pages, no technical background needed.**

---

## There is a finding. It is not the one the project set out to produce.

The project set out to count how often a published decision rule decides
differently today than it decided at the time. **That count has not been
computed, and will not be until the validation problem below is resolved.**

What was found instead concerns the yardstick.

## The short version

To check its own arithmetic, this project compares its answers against
`SAHMREALTIME` — a real-time recession-indicator series published by the Federal
Reserve Bank of St. Louis. If our numbers reproduce theirs, our method works.

They almost do. Out of 528 months, **525 match exactly.**

The three that do not are all Decembers. Chasing them turned up something
awkward: FRED's December figures reflect a data revision that arrives *a month
after December is published*. So a second comparison was run using that later
vintage throughout.

That version reproduced all three Decembers — and broke **twenty-five
Novembers**, which the first version had got right.

Neither set overlaps the other. Neither is scattered. One convention is exactly
right for every November and wrong for three Decembers; the other is exactly
right for every December and wrong for twenty-five Novembers.

**Conclusion: `SAHMREALTIME` cannot be reproduced from the underlying vintage
record by any single consistent rule about which vintage to use.**

## The discrepancy now has a name

That conclusion still stands. What has changed since it was written is that the
mixing is no longer unexplained.

Each year the Bureau of Labor Statistics restates several years of seasonally
adjusted history in one go. That revision does not arrive on a fixed date: across
this sample it landed with the **January** release in most years and with the
**February** release in a few.

November and December sit on opposite sides of that event, and which one breaks
follows from the calendar alone:

- A **January** landing is already visible on the day December is published, so
  December agrees — and it is one release too late for November, so November
  breaks.
- A **February** landing is too late for December, so December breaks — and
  November is unaffected.

The prediction was written down before the years were counted. It holds without
exception: **all 3 December failures fall in February-landing years, all 25
November failures fall in January-landing years, and no failure is left over.**
In all 44 years the annual revision moved a month's figure past the tolerance if
and only if that month failed.

So the two conventions were never each "right sometimes". Each was tracking a
different side of an event whose date moves.

**This is an inference from the public record, not a description confirmed by
the publisher.** It shows the mixing is systematic and says what it tracks. It
does not show that FRED builds the series this way, and nothing here says the
series is wrong.

**It changes no verdict.** Gate 2 failed, and the preregistration binds on the
verdict rather than on how well the failure is now understood. Explaining a
failed check and then treating the explanation as a pass is the exact move the
check exists to prevent — and it is more tempting now than it was when the
failure looked arbitrary.

The preregistration had guessed wrong about this in advance. Written before
either gate ran, it said that if both conventions failed, "something else is
wrong and neither convention explains it." Something else was not wrong, and the
calendar does explain it. That correction is recorded in the preregistration
itself, as Amendment 3, rather than only in the documents it happens to suit.

## Why that matters beyond this project

`SAHMREALTIME` is not an obscure series. It is the real-time version of a widely
cited recession indicator, published by a Federal Reserve bank, and it is exactly
the kind of series a careful analyst reaches for *precisely because* it promises
to reflect what was knowable at the time.

This project's whole premise is that the record changes after you read it. The
first thing that premise caught was the benchmark meant to verify it.

**This is not an accusation.** The most likely explanation is mundane: the annual
seasonal-adjustment revision landed in February in some years of the sample and
in January in others, and a monthly construction process would inherit that
timing. Nothing here shows the series is wrong. It shows it is not reproducible
from the public vintage record without knowing a construction detail that is not
documented alongside it.

## What was deliberately not done

The temptation at every step was to make the check pass:

- **The tolerance was not widened.** That was forbidden in writing on 2026-08-26,
  before any gate had run, precisely because it is the obvious escape.
- **The method was not changed to match the benchmark.** It would have taken one
  line.
- **A third convention was not tried.** Two is already the edge. A third, chosen
  after seeing which months failed, is gate-shopping with extra steps.
- **The failure was not reported as a pass with a footnote.**

The preregistration says that if this check fails, the failure is published and
the downstream extension does not run. It failed. Both consequences hold.

## What happens next

The finding above is real and publishable on its own. Resolving the validation
problem needs one of:

1. **A different benchmark** for the rule, if one exists that is reproducible.
2. **Documentation** of how `SAHMREALTIME` is constructed, which would turn this
   from an unexplained discrepancy into a known one. *Half done.* The
   discrepancy is now characterised from the vintage record — see above — but
   characterised by us, not confirmed by the publisher. Closing it properly
   means asking them.
3. **Accepting that the rule cannot be externally validated**, and reporting the
   primary outcome with that limitation stated in the headline rather than the
   appendix — a materially weaker claim, and it would have to be labelled as one.

None of the three is chosen yet, and the choice is not a technical one. Route 3
is now the cheapest it will ever look, which is a reason to be careful about it
rather than a reason to take it.

---

*Last updated 2026-08-30. Gate 1: passed, 0 of 111,948 — though see METHODS.md
on what that run did and did not test. Gate 2: failed, 3 of 528. Gate 2b
(post-hoc): failed, 25 of 528. Failure pattern: fully accounted for by the BLS
annual revision calendar, 28 of 28. Primary outcome: not computed.*
