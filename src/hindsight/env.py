"""Load .env into the process environment, if one exists.

No dependency, no magic: `KEY=value` lines, `#` comments, blank lines ignored.
Values already present in the environment win, so an explicitly exported
variable is never silently overridden by a stale file.

.env is gitignored. Nothing in this project ever logs the values it reads.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path | None = None) -> list[str]:
    """Populate os.environ from a .env file. Returns the names it set."""
    path = path or ROOT / ".env"
    if not path.exists():
        return []

    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
