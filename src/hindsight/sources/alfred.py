"""ALFRED (Archival FRED) client.

FRED serves the current value of a series. ALFRED serves every value the series
has ever had, each tagged with the interval during which it was the published
figure. That archive is the reason this project can be checked rather than
believed: for the US series, someone else has already recorded what was knowable
when, so our reconstruction can be marked against theirs (Gate 1).

An api_key is required and free. It is read from HINDSIGHT_FRED_API_KEY and is
the only credential in the project.
"""

from __future__ import annotations

import datetime as dt
import os
import time
from dataclasses import dataclass
from typing import Iterable, Iterator

import httpx

BASE = "https://api.stlouisfed.org/fred"

# ALFRED's sentinels for "since the beginning of the archive" and "until further
# notice". These are the API's own values, not ours.
ARCHIVE_START = "1776-07-04"
ARCHIVE_END = "9999-12-31"


@dataclass(frozen=True)
class RealtimeInterval:
    """One value of one reference period, and the window it was current for."""

    series_id: str
    ref_period_start: dt.date
    value: float | None
    realtime_start: dt.date  # the day this value became the published figure
    realtime_end: dt.date


class AlfredError(RuntimeError):
    pass


class Alfred:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: httpx.Client | None = None,
        min_interval_s: float = 0.6,
    ) -> None:
        self.api_key = api_key or os.environ.get("HINDSIGHT_FRED_API_KEY", "")
        if not self.api_key:
            raise AlfredError(
                "HINDSIGHT_FRED_API_KEY is unset. Get a free key at "
                "https://fredaccount.stlouisfed.org/apikeys"
            )
        self._client = client or httpx.Client(timeout=60.0)
        # FRED publishes a per-minute request limit. Rather than encode a number
        # that may change, throttle conservatively and back off on 429.
        self._min_interval_s = min_interval_s
        self._last_call = 0.0

    def _get(self, path: str, **params: object) -> dict:
        wait = self._min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        for attempt in range(5):
            r = self._client.get(
                f"{BASE}/{path}",
                params={"api_key": self.api_key, "file_type": "json", **params},
            )
            self._last_call = time.monotonic()
            if r.status_code == 429:
                time.sleep(2**attempt)
                continue
            if r.status_code >= 400:
                raise AlfredError(f"{path} -> {r.status_code}: {r.text[:300]}")
            return r.json()
        raise AlfredError(f"{path}: rate limited after 5 attempts")

    def vintage_dates(self, series_id: str) -> list[dt.date]:
        """Every date on which this series was republished."""
        payload = self._get("series/vintagedates", series_id=series_id, limit=10_000)
        return [dt.date.fromisoformat(d) for d in payload.get("vintage_dates", [])]

    def realtime_intervals(self, series_id: str) -> Iterator[RealtimeInterval]:
        """The full archive, as (reference period, value, validity window) rows.

        output_type=1 is 'observations by real-time period': one row per distinct
        value a reference period has held, with the dates it held it. That maps
        one-to-one onto the append-only table -- realtime_start is the vintage
        date -- and it is the only request shape that returns the whole history
        without enumerating vintages ourselves.
        """
        payload = self._get(
            "series/observations",
            series_id=series_id,
            realtime_start=ARCHIVE_START,
            realtime_end=ARCHIVE_END,
            output_type=1,
        )
        for o in payload["observations"]:
            yield RealtimeInterval(
                series_id=series_id,
                ref_period_start=dt.date.fromisoformat(o["date"]),
                # ALFRED encodes a period published as missing with ".", which is
                # not the same as a period we failed to collect. Stored NULL,
                # never imputed.
                value=None if o["value"] == "." else float(o["value"]),
                realtime_start=dt.date.fromisoformat(o["realtime_start"]),
                realtime_end=dt.date.fromisoformat(o["realtime_end"]),
            )

    def latest_vintage(self, series_id: str) -> dt.date:
        """The most recent date on which this series was republished.

        Asking for a series 'as of today' is wrong whenever today is not itself
        a vintage date, which is most days. Ask for its latest vintage instead.
        """
        dates = self.vintage_dates(series_id)
        if not dates:
            raise AlfredError(f"{series_id}: no vintage dates")
        return dates[-1]

    def as_of(self, series_id: str, vintage: dt.date) -> dict[dt.date, float]:
        """The series exactly as ALFRED says it read on `vintage`.

        Gate 1 marks our own reconstruction against this. It is deliberately a
        separate request shape from realtime_intervals: if both were derived the
        same way, agreement between them would prove nothing.

        The name of the value column is *discovered, not assumed*. Under
        output_type=2 each vintage's values arrive in their own column, and the
        first version of this method guessed the naming from the documentation.
        It guessed wrong, and the failure mode was an empty dict -- which
        reconstructs as 'nothing was published that day' and reads as a gap in
        collection rather than a bug in the parser. Anything that turns our error
        into apparent missing data gets an explicit check, not a default.
        """
        payload = self._get(
            "series/observations",
            series_id=series_id,
            vintage_dates=vintage.isoformat(),
            output_type=2,
        )
        observations = payload.get("observations", [])
        if not observations:
            raise AlfredError(
                f"{series_id}: no observations returned for vintage {vintage}. "
                f"Is {vintage} actually a vintage date for this series?"
            )

        columns = [k for k in observations[0] if k != "date"]
        if len(columns) != 1:
            raise AlfredError(
                f"{series_id}: expected one value column for vintage {vintage}, "
                f"got {columns!r}"
            )
        column = columns[0]

        out: dict[dt.date, float] = {}
        for o in observations:
            raw = o.get(column)
            if raw in (None, "", "."):
                continue
            out[dt.date.fromisoformat(o["date"])] = float(raw)
        return out


def to_db_rows(
    intervals: Iterable[RealtimeInterval], *, frequency: str
) -> Iterator[dict]:
    """Flatten archive intervals into append-only observation rows.

    One row per (series, reference period, vintage date). A later restatement of
    the same period arrives as a different vintage_date and therefore a different
    row; there is no path here that overwrites an earlier one.
    """
    for iv in intervals:
        yield {
            "series_id": iv.series_id,
            "ref_period_start": iv.ref_period_start,
            "ref_period_end": _period_end(iv.ref_period_start, frequency),
            "vintage_date": iv.realtime_start,
            "value": iv.value,
            "run_label": None,
        }


def _period_end(start: dt.date, frequency: str) -> dt.date:
    """Last day of the reference period beginning at `start`."""
    months = {"M": 1, "Q": 3, "A": 12}.get(frequency)
    if months is None:
        raise ValueError(f"unsupported frequency {frequency!r}")
    y, m = divmod(start.month - 1 + months, 12)
    nxt = dt.date(start.year + y, m + 1, 1)
    return nxt - dt.timedelta(days=1)
