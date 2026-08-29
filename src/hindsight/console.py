"""Make stdout carry the characters the scripts actually print.

Every script here prints em dashes, ellipses and arrows. On Windows the console
encoding defaults to cp1252, which cannot encode them, so `print` raises
UnicodeEncodeError *after* the useful work has been done and the exit status
becomes a crash rather than a verdict.

That failure mode matters more than it looks. `scripts/smoke.py` exists to catch
a quiet parse failure before an ingest; a smoke run that dies at the fifth check
because of a dash reports nothing about the sixth. A diagnostic that cannot
print is a diagnostic that did not run.

Reconfiguring is preferred over dropping the characters: replacing them would
hide the problem on the machine where it happens and leave the output subtly
different from the output the same script produces elsewhere.
"""

from __future__ import annotations

import sys


def use_utf8() -> None:
    """Force UTF-8 on stdout/stderr where the stream allows it.

    Idempotent, and a no-op on streams that are already UTF-8 or that do not
    support reconfiguration (a pipe wrapped by a test harness, for instance).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") == "utf8":
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            # An unreconfigurable stream is not a reason to abort a run. The
            # worst case is the same crash we had before, on the same character.
            pass
