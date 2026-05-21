#!/usr/bin/env python3
"""Generate a bcrypt hash for ROOT_PASSWORD in .env."""

import sys

import bcrypt


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/hash_root_password.py 'your-secret-password'", file=sys.stderr)
        return 1
    password = sys.argv[1]
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    print(hashed.decode("utf-8"))
    print("\nAdd to .env:\nROOT_PASSWORD=" + hashed.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
