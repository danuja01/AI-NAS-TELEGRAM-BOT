"""
Fail fast if the application cannot be imported (same check as CI smoke tests).

Usage:
  python scripts/smoke_imports.py
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import-only check: no real tokens required (config.validate_config is skipped).
os.environ.setdefault("SMOKE_IMPORT_ONLY", "1")


def main() -> int:
    try:
        importlib.import_module("bot")
    except Exception as exc:
        print(f"smoke: import failed: {exc}", file=sys.stderr)
        return 1
    print("smoke: imports OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
