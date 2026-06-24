#!/usr/bin/env python3
"""Run a command while holding an exclusive lock on {path}.lock (fcntl, macOS/Linux)."""
from __future__ import annotations

import fcntl
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: json-flock.py <json-path> <command> [args...]", file=sys.stderr)
        return 2
    target = Path(sys.argv[1])
    cmd = sys.argv[2:]
    lock_path = target.with_suffix(target.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
