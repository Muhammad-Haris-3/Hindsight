"""The preregistration is enforced, not merely published.

A document that states a threshold while the code uses another is worse than no
document, because it looks like a commitment. This test parses
PREREGISTRATION.md and fails if any constant there disagrees with
`hindsight.prereg` -- in either direction. Editing one without the other breaks
the build, which is the only version of a commitment that means anything.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest

from hindsight import prereg

DOC = Path(__file__).resolve().parents[1] / "PREREGISTRATION.md"

# (symbol referenced in the doc's third column, value as rendered in the second)
EXPECTED = [
    ("prereg.WINDOW_START", "1976-01", dt.date(1976, 1, 1)),
    ("prereg.WINDOW_END", "2019-12", dt.date(2019, 12, 1)),
    ("prereg.FREEZE_DATE", "2026-09-01", dt.date(2026, 9, 1)),
    ("prereg.SAHM_THRESHOLD", "0.50", Decimal("0.50")),
    ("prereg.ARITHMETIC", "decimal-exact", "decimal-exact"),
    ("prereg.BOUNDARY_INCLUSIVE", "True", True),
    ("prereg.GAP_PRECISION", "2", 2),
    ("prereg.GAP_ROUNDING", "ROUND_HALF_UP", "ROUND_HALF_UP"),
    ("prereg.SAHM_SHORT_WINDOW", "3", 3),
    ("prereg.SAHM_LOOKBACK", "12", 12),
    ("prereg.RECONSTRUCTION_TOL", "0.005", Decimal("0.005")),
    ("prereg.MIN_VINTAGE_COVERAGE", "0.95", 0.95),
]


@pytest.fixture(scope="module")
def rows() -> list[str]:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    return [ln for ln in lines if ln.startswith("|")]


@pytest.mark.parametrize("symbol,rendered,value", EXPECTED, ids=lambda x: str(x))
def test_constant_matches_document(symbol, rendered, value, rows):
    matching = [r for r in rows if symbol in r]
    assert matching, f"{symbol} is not cited in PREREGISTRATION.md"
    assert any(f"`{rendered}`" in r for r in matching), (
        f"{symbol} is cited in the document but not with the value {rendered!r}. "
        f"Rows found: {matching}"
    )

    attr = symbol.split(".", 1)[1]
    assert getattr(prereg, attr) == value


def test_series_list_is_closed(rows):
    """Every studied series is named in the document, and no others exist."""
    cited = set()
    for r in rows:
        for m in re.finditer(r"`([A-Z][A-Z0-9]{3,})`", r):
            cited.add(m.group(1))
    for series_id in prereg.SERIES:
        assert series_id in cited, f"{series_id} is used in code but not preregistered"


def test_amendments_section_exists():
    """Amendments are appended, never edited in place. The heading must survive."""
    text = DOC.read_text(encoding="utf-8")
    assert "## Amendments" in text
    assert text.index("## Amendments") > text.index("## H0")


def test_every_test_file_the_document_cites_exists():
    """A document may not point at an enforcement that was never written.

    PREREGISTRATION.md names the test files that hold it to its own terms. A
    named file that does not exist reads exactly like one that does -- the claim
    is on the page either way -- and it is the cheapest possible way for a
    commitment to become decoration. This test caught one: the document had
    cited `tests/test_validation_gates.py` since M0, and it did not exist.
    """
    cited = set(re.findall(r"`(tests/[A-Za-z0-9_]+\.py)`", DOC.read_text(encoding="utf-8")))
    assert cited, "the document cites no enforcement at all"
    for path in sorted(cited):
        assert (DOC.parent / path).exists(), (
            f"PREREGISTRATION.md cites {path}, which does not exist. Either write "
            "it or stop claiming it."
        )


def test_window_precedes_freeze():
    assert prereg.WINDOW_START < prereg.WINDOW_END < prereg.FREEZE_DATE


def test_pandemic_excluded_from_primary_window():
    """The window ends before 2020 by design; see PREREGISTRATION.md."""
    assert prereg.WINDOW_END < dt.date(2020, 1, 1)
