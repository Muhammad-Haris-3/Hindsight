"""The Sahm rule, and only the Sahm rule.

Three-month moving average of the unemployment rate, minus the minimum of that
moving average over the preceding twelve months. Fires at >= 0.50pp.

This module is deliberately ignorant of vintages. It is handed a series of
(month, value) pairs and says what the rule does with them. Which pairs it is
handed -- what was knowable then, or what is known now -- is the entire question
and belongs to the caller.

Arithmetic is exact decimal, not binary float. This is not fastidiousness. The
unemployment rate is published to one decimal place, the threshold is exactly
0.50, and real prints land exactly on it. Under binary floats two months with an
identical gap of 0.50 can return different answers, because 4.4 - 3.9 is
0.5000000000000004 in one summation order and 0.4999999999999996 in another. A
finding about revisions moving decisions would then be partly a finding about
IEEE 754. See PREREGISTRATION.md, `prereg.ARITHMETIC`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from hindsight import prereg


QUANTUM = Decimal(1).scaleb(-prereg.GAP_PRECISION)  # Decimal("0.01")


@dataclass(frozen=True)
class SahmPoint:
    month: dt.date
    short_avg: Decimal | None
    prior_min: Decimal | None
    gap: Decimal | None       # rounded to prereg.GAP_PRECISION; decides `fires`
    fires: bool | None        # None = not computable from the values supplied
    gap_exact: Decimal | None = None  # unrounded, published for transparency


def compute(
    observations: dict[dt.date, float | str | Decimal],
    *,
    threshold: Decimal = prereg.SAHM_THRESHOLD,
    short_window: int = prereg.SAHM_SHORT_WINDOW,
    lookback: int = prereg.SAHM_LOOKBACK,
) -> list[SahmPoint]:
    """Evaluate the rule for every month in `observations`.

    `observations` maps the first day of a reference month to the unemployment
    rate as published in whichever vintage the caller chose. Months absent from
    the mapping are absent, not zero: any window overlapping a gap yields
    `fires=None` rather than a value computed from fewer months than the rule
    specifies. Silently shortening the window is how a gap in collection turns
    into a firing that never happened.
    """
    values = {m: _dec(v) for m, v in observations.items()}
    months = sorted(values)
    window_n = Decimal(short_window)

    short: dict[dt.date, Decimal] = {}
    for i, m in enumerate(months):
        window = months[max(0, i - short_window + 1) : i + 1]
        if len(window) < short_window or not _contiguous(window):
            continue
        short[m] = sum((values[w] for w in window), Decimal(0)) / window_n

    out: list[SahmPoint] = []
    for i, m in enumerate(months):
        avg = short.get(m)
        if avg is None:
            out.append(SahmPoint(m, None, None, None, None))
            continue

        prior_months = months[max(0, i - lookback) : i]
        prior = [short[p] for p in prior_months if p in short]
        if len(prior) < lookback or not _contiguous(prior_months):
            out.append(SahmPoint(m, avg, None, None, None))
            continue

        prior_min = min(prior)
        exact = avg - prior_min
        # Amendment 1: the rule fires on the gap as published, not on digits the
        # source never had. Half-up, matching how the benchmark is rounded.
        gap = exact.quantize(QUANTUM, rounding=ROUND_HALF_UP)
        out.append(SahmPoint(m, avg, prior_min, gap, gap >= threshold, exact))

    return out


def _dec(v: float | str | Decimal) -> Decimal:
    """Convert to Decimal via str, so 4.4 means 4.4 and not 4.40000000000000036."""
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _contiguous(months: list[dt.date]) -> bool:
    """True if `months` are consecutive calendar months with no gap."""
    for a, b in zip(months, months[1:]):
        carry, nxt = divmod(a.month, 12)
        if (b.year, b.month) != (a.year + carry, nxt + 1):
            return False
    return True
