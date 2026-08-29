"""Constants fixed by PREREGISTRATION.md.

Nothing in this module may be changed without an amendment appended to that
document. `tests/test_preregistration.py` parses the markdown table and asserts
every value here matches it, so drift in either direction fails the build.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Final

# --- study window -----------------------------------------------------------
WINDOW_START: Final = dt.date(1976, 1, 1)
WINDOW_END: Final = dt.date(2019, 12, 1)
FREEZE_DATE: Final = dt.date(2026, 9, 1)

# --- Sahm rule --------------------------------------------------------------
SAHM_THRESHOLD: Final = Decimal("0.50")   # percentage points, exact
SAHM_SHORT_WINDOW: Final = 3      # months in the moving average
SAHM_LOOKBACK: Final = 12         # months of preceding minima

# --- what counts ------------------------------------------------------------
MATERIAL_IS_DECISION_FLIP: Final = True
RECONSTRUCTION_TOL: Final = Decimal("0.005")  # percentage points

# Exact decimal, never binary float. The threshold is hit exactly by real
# prints; under IEEE 754 the boundary case is decided by summation order.
ARITHMETIC: Final = "decimal-exact"
# A gap of exactly 0.50 fires. Sahm's own definition is >= , and the
# boundary is not rare enough to leave to a convention chosen later.
BOUNDARY_INCLUSIVE: Final = True

# Amendment 1. The benchmark is published to two decimal places; an exact gap
# carries digits the source never had. The gap is rounded before it meets the
# threshold, so the rule fires on the number an analyst would read off the page.
GAP_PRECISION: Final = 2
GAP_ROUNDING: Final = "ROUND_HALF_UP"
MIN_VINTAGE_COVERAGE: Final = 0.95

# --- series, fixed in full ---------------------------------------------------
SERIES: Final = {
    "UNRATE": "primary",
    "PAYEMS": "secondary",
    "GDPC1": "secondary",
    "INDPRO": "secondary",
    "RSAFS": "control",
}

# The series FRED publishes that our reconstruction must reproduce (Gate 2).
GATE2_BENCHMARK_SERIES: Final = "SAHMREALTIME"

GATE1_SAMPLE_SIZE: Final = 200

# Amendment 2. Designed AFTER Gate 2 failed, and labelled as such wherever it is
# reported. The benchmark reflects the annual seasonal revision that lands one
# release after a December is published; this offset applies that convention
# uniformly rather than carving out the months where it happens to help.
GATE2B_RELEASE_OFFSET: Final = 1
GATE2B_IS_POST_HOC: Final = True
